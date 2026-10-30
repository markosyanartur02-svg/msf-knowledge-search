"""Build the offline search index from the parsed Markdown files.

Run once (internet is only needed the very first time, to download the two models
into ./index/; every later rebuild works offline):

    python prep.py

Steps:
  1. Load every Markdown file plus its genre/language from documentation.csv
     and a readable title (from the original HTML <title>, or the first heading).
  2. Drop exact duplicates (e.g. the 18 identical msfaccess.org homepage scrapes).
  3. Remove boilerplate lines that repeat across many documents (menus, banners).
  4. Split each document into ~200-word passages, keeping the section heading.
  5. Build a BM25 keyword index and multilingual embeddings for the passages.

Everything the search needs is written to ./index/, including a local copy of the
model, so the folder can be copied to an offline machine as-is.
"""
import csv
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter

import numpy as np
from scipy import sparse

from common import (CURRENT_YEAR, EMBED_MODEL, EVIDENCE_LABELS, EVIDENCE_LEVELS, INDEX_DIR,
                    METADATA_CSV, MODEL_DIR, ORIGINAL_DIR, PARSED_DIR, RERANK_MODEL, RERANKER_DIR, strip_accents,
                    tokenize)

CHUNK_WORDS = 150          # target passage length
WINDOW_OVERLAP = 30        # overlap when a single paragraph is longer than a passage
MIN_CHUNK_WORDS = 30       # smaller trailing pieces are merged into the previous passage
BOILERPLATE_MIN_DOCS = 8   # a line seen in this many documents is treated as boilerplate
BM25_K1, BM25_B = 1.2, 0.75

_HEADING = re.compile(r"^#{1,6}\s+(.*)")


def load_metadata() -> dict:
    with open(METADATA_CSV, encoding="utf-8-sig") as f:
        return {row["id"]: row for row in csv.DictReader(f)}


# medicalguidelines.msf.org guide codes (from the page address) -> guide name per language, so a
# chapter titled "9.2 Conventional treatment regimens" becomes "Tuberculosis › 9.2 Conventional ...".
GUIDE_NAMES = {
    "CG": {"english": "Clinical guidelines", "francais": "Guide clinique et thérapeutique",
           "spanish": "Guía clínica y terapéutica"},
    "EssDr": {"english": "Essential drugs", "francais": "Médicaments essentiels",
              "spanish": "Medicamentos esenciales"},
    "TUB": {"english": "Tuberculosis", "francais": "Tuberculose"},
    "ONC": {"english": "Essential obstetric and newborn care",
            "francais": "Soins obstétricaux et néonatals essentiels"},
    "CHOL": {"english": "Management of a cholera epidemic", "francais": "Prise en charge d'une épidémie de choléra"},
    "mme": {"english": "Management of a measles epidemic", "francais": "Prise en charge d'une épidémie de rougeole"},
}


def html_metadata(path) -> tuple:
    """(title without the " | MSF" suffix, publication year or None) from the original HTML."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = (re.search(r'property="og:title"\s+content="([^"]+)"', raw)
             or re.search(r"<title[^>]*>(.*?)</title>", raw, re.S))
    title = " ".join(html.unescape(match.group(1)).split(" | ")[0].split()) if match else ""
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"', raw)
    guide = re.search(r"medicalguidelines\.msf\.org/\w+/viewport/(\w+)/(\w+)/", canonical.group(1)) if canonical else None
    if guide and title:
        name = GUIDE_NAMES.get(guide.group(1), {}).get(guide.group(2))
        same = lambda s: strip_accents(s.lower().replace("’", "'"))  # noqa: E731
        if name and same(name) not in same(title):
            title = f"{name} › {title}"
    year = (re.search(r'"datePublished"\s*:\s*"(\d{4})', raw)
            or re.search(r'citation_(?:publication_)?date"\s+content="(\d{4})', raw)
            or re.search(r'article:published_time"\s+content="(\d{4})', raw)
            or re.search(r"(?:Last Update|Mises? à jour|Actualizaci[oó]n)[^<\d]{0,40}(\d{4})", raw))
    return title, int(year.group(1)) if year else None


def text_year(text: str):
    """Most recent plausible year in the first page of text (publication or report year)."""
    years = [int(y) for y in re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", text[:3000])]
    years = [y for y in years if y <= CURRENT_YEAR]
    return max(years) if years else None


def data_quality(text: str, noise_share: float, original) -> float:
    """0-1 score of how cleanly the text was extracted (OCR damage, tables, menus, scans)."""
    words = text.split()
    n_words = max(len(words), 1)
    lines = [line for line in text.splitlines() if line.strip()]
    glued = sum(len(w) > 25 for w in words) / n_words
    menu_like = sum(len(line.split()) <= 3 for line in lines) / max(len(lines), 1)
    score = 1.0 - 0.5 * noise_share - min(0.4, glued * 10) - 0.5 * max(0.0, menu_like - 0.4)
    if len(words) < 200:      # landing pages, tables of contents
        score -= 0.3
    if original and original.suffix == ".pdf" and original.stat().st_size / n_words > 4000:
        score -= 0.3          # mostly images: scanned or poorly extracted PDF
    return round(min(1.0, max(0.05, score)), 2)


_LABELS = {"policy forum", "editorial", "research article", "original article", "research", "protocol",
           "perspectives", "perspective", "commentary", "review", "letter", "short report", "abstract",
           "authors", "citation", "open access", "articles", "article", "contents", "case report",
           "original research", "research paper", "brief report", "viewpoint", "presentation powerpoint"}
_JOURNAL_HEADER = re.compile(
    r"doi|vol\.|issn|http|www\.|©|journal|\d{4};|\(\d{4}\)\s*\d+:|permits use|creative commons|"
    r"open access|conflict of interest|provisional pdf|society of america|copy is furnished|"
    r"personal use|charity reg|submissions should|citation:|cite this|item type|page \d|\d+ of \d+|"
    r"published:|received:|editors?:|reviewed by|public health action|clinical infectious diseases|"
    r"open forum|lancet|engl j med|new engl|statistical methods|tropical medicine and|bmc |plos|"
    r"infection control|emerging infectious|bull world health|these abstracts|mja \d|minerva", re.I)
_AUTHOR_LINE = re.compile(r"[a-zÀ-ɏ]\d|\d,\d|\*|§|et al|@|university|department|institute", re.I)


def _title_like(line: str) -> bool:
    words = re.findall(r"[^\W\d_]{2,}", line)
    single_letters = re.findall(r"\b[^\W\d_]\b", line)
    return (len(words) >= 1 and len(single_letters) < 4 and line.lower().strip(" :.") not in _LABELS
            and not _JOURNAL_HEADER.search(line) and not _AUTHOR_LINE.search(line))


_REPORT_COVER = re.compile(r"\b(international\s+)?(activity|financial)\s+report\s*((?:19|20)\d\d(?:\s*-\s*(?:19|20)\d\d)?)",
                           re.I)


def markdown_title(text: str) -> str:
    """Best guess at a title: report cover, first heading, block of capitals, or wrapped title lines."""
    cover = _REPORT_COVER.search(" ".join(text[:600].split()))
    if cover:  # e.g. "International / Activity / Report 2014" above "The MSF Charter"
        scope = "International " if cover.group(1) else ""
        return f"MSF {scope}{cover.group(2).title()} Report {cover.group(3).replace(' ', '')}"
    lines = [line.strip(" *#-|>\t") for line in text.splitlines() if line.strip(" *#-|>\t")][:30]
    for line in lines[:10]:
        heading = _HEADING.match(line)
        if heading:
            return heading.group(1).strip(" *#")[:150]
    candidates = [line for line in lines if _title_like(line)]
    if not candidates:
        return ""
    # Report covers: several short ALL-CAPS lines ("INTERNATIONAL / FINANCIAL / REPORT 2021").
    caps = []
    for line in candidates:
        if not line.isupper() or len(caps) >= 4:
            break
        caps.append(line)
    if len(" ".join(caps).split()) >= 3:
        return " ".join(" ".join(caps).split()[:14]).title()
    # Articles: title wrapped over several lines, ending before the author line.
    start = next((i for i, line in enumerate(lines) if _title_like(line) and len(line.split()) >= 3), None)
    if start is None:
        return candidates[0][:150]
    title = lines[start]
    for line in lines[start + 1:start + 4]:
        continues = line[:1].islower() or (len(line.split()) <= 10 and not title.endswith((".", "?", "!")))
        if not _title_like(line) or not continues or len((title + " " + line).split()) > 25:
            break
        title += " " + line
    return title[:200]


def load_documents() -> list:
    metadata = load_metadata()
    documents = []
    for md_path in sorted(PARSED_DIR.glob("*.md")):
        doc_id = md_path.stem
        text = md_path.read_text(encoding="utf-8", errors="replace")
        original = next(ORIGINAL_DIR.glob(doc_id + ".*"), None)
        title, year = html_metadata(original) if original and original.suffix == ".html" else ("", None)
        info = metadata.get(doc_id, {})
        genre = info.get("genre", "Unknown")
        evidence = EVIDENCE_LEVELS.get(genre, 2)
        documents.append({
            "id": doc_id,
            "title": title or markdown_title(text) or doc_id,
            "genre": genre,
            "language": info.get("language", "?"),
            # Guideline chapters are living documents: years in their text are citations, not age.
            "year": year if genre == "Clinical Guideline Chapter" else year or text_year(text),
            "evidence": evidence,
            "evidence_label": EVIDENCE_LABELS[evidence],
            "original_file": original.name if original else "",
            "parsed_file": md_path.name,
            "text": text,
            "_original": original,
        })
    return documents


def drop_exact_duplicates(documents: list) -> list:
    """Keep the first copy of identical texts and record the other ids on it."""
    kept, by_hash = [], {}
    for doc in documents:
        digest = hashlib.md5(" ".join(doc["text"].split()).encode()).hexdigest()
        if digest in by_hash:
            by_hash[digest]["duplicates"].append(doc["id"])
            continue
        doc["duplicates"] = []
        by_hash[digest] = doc
        kept.append(doc)
    return kept


def remove_boilerplate(documents: list) -> set:
    """Delete lines (menus, cookie/app banners, repeated prefaces) shared by many documents."""
    line_counts = Counter()
    for doc in documents:
        line_counts.update({line.strip() for line in doc["text"].splitlines() if line.strip()})
    boilerplate = {line for line, n in line_counts.items()
                   if n >= BOILERPLATE_MIN_DOCS and not line.startswith("#")}
    for doc in documents:
        doc["text"] = "\n".join(line for line in doc["text"].splitlines()
                                if line.strip() not in boilerplate)
    return boilerplate


def chunk_document(text: str) -> list:
    """Split text into ~CHUNK_WORDS passages on paragraph boundaries, tracking the section heading."""
    chunks, buffer, buffer_section, section = [], [], "", ""

    def flush():
        nonlocal buffer
        if buffer:
            chunks.append({"section": buffer_section, "words": buffer})
            buffer = []

    for paragraph in re.split(r"\n\s*\n", text):
        lines = paragraph.strip().splitlines()
        if not lines:
            continue
        heading = _HEADING.match(lines[0].strip())
        if heading:
            flush()
            section = heading.group(1).strip(" *#")[:120]
            lines = lines[1:]
        words = " ".join(lines).split()
        if not words:
            continue
        if buffer and len(buffer) + len(words) > CHUNK_WORDS:
            flush()
        if not buffer:
            buffer_section = section
        if len(words) <= CHUNK_WORDS:
            buffer.extend(words)
            continue
        # Paragraph longer than a passage (common in PDFs): cut it into overlapping windows.
        flush()
        step = CHUNK_WORDS - WINDOW_OVERLAP
        for start in range(0, len(words), step):
            window = words[start:start + CHUNK_WORDS]
            chunks.append({"section": section, "words": window})
            if start + CHUNK_WORDS >= len(words):
                break
    flush()

    merged = []
    for chunk in chunks:
        if merged and len(chunk["words"]) < MIN_CHUNK_WORDS:
            merged[-1]["words"].extend(chunk["words"])
        else:
            merged.append(chunk)
    return [{"section": c["section"], "text": " ".join(c["words"])} for c in merged]


def is_noise(text: str) -> bool:
    """Reference lists, number tables and OCR text with glued words: kept, but not searched."""
    words = text.split()
    n = max(len(words), 1)
    references = len(re.findall(r"et al|doi|PMID|https?://|\b(?:19|20)\d{2}\b[;:.]|\[\d+\]|\d+\(\d+\):\d+",
                                text))
    numeric = sum(bool(re.fullmatch(r"[\d.,%()\-–+/<>=±|:;]+", w)) for w in words) / n
    glued = sum(len(w) > 25 for w in words) / n
    return references / n * 100 > 4 or numeric > 0.35 or glued > 0.04


def build_bm25(token_lists: list):
    """BM25 weights as a sparse (passages x terms) matrix: a query score is a column sum."""
    vocab, rows, cols, counts = {}, [], [], []
    for row, tokens in enumerate(token_lists):
        for token, count in Counter(tokens).items():
            rows.append(row)
            cols.append(vocab.setdefault(token, len(vocab)))
            counts.append(count)
    rows, cols = np.array(rows), np.array(cols)
    tf = np.array(counts, dtype=np.float32)
    n_docs = len(token_lists)
    lengths = np.array([len(t) for t in token_lists], dtype=np.float32)
    doc_freq = np.bincount(cols, minlength=len(vocab))
    idf = np.log1p((n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
    norm = BM25_K1 * (1 - BM25_B + BM25_B * lengths[rows] / lengths.mean())
    weights = idf[cols] * tf * (BM25_K1 + 1) / (tf + norm)
    matrix = sparse.csc_matrix((weights.astype(np.float32), (rows, cols)),
                               shape=(n_docs, len(vocab)))
    return matrix, vocab


def build_spelling(texts: list, vocab: dict) -> dict:
    """Indexed term -> [most common spelling in the text, occurrences], for "did you mean"."""
    words = Counter(w for text in texts for w in re.findall(r"\w+", text.lower()) if not w.isdigit())
    best = {}  # term -> (spelling, its count, total count of the term)
    for word, count in words.items():
        tokens = tokenize(word)
        if len(tokens) != 1 or tokens[0] not in vocab:
            continue
        spelling, top, total = best.get(tokens[0], ("", 0, 0))
        if count > top:
            spelling, top = word, count
        best[tokens[0]] = (spelling, top, total + count)
    return {term: [spelling, total] for term, (spelling, _, total) in best.items()}


def main():
    start = time.time()
    INDEX_DIR.mkdir(exist_ok=True)

    documents = load_documents()
    n_loaded = len(documents)
    documents = drop_exact_duplicates(documents)
    boilerplate = remove_boilerplate(documents)
    # Saved so the reader view (fileserver.py) can show documents without menus and banners.
    (INDEX_DIR / "boilerplate.json").write_text(json.dumps(sorted(boilerplate), ensure_ascii=False))
    print(f"Loaded {n_loaded} documents, {n_loaded - len(documents)} exact duplicates dropped, "
          f"{len(boilerplate)} boilerplate lines removed")

    chunks = []
    for doc_index, doc in enumerate(documents):
        passages = chunk_document(doc["text"]) or [{"section": "", "text": doc["title"]}]
        for passage in passages:
            # Guideline chapters are curated: their dosing tables and cited sections are the
            # content clinicians need, so the reference/table filter never applies to them.
            passage["noise"] = doc["evidence"] < 5 and is_noise(passage["text"])
        noise_share = sum(p["noise"] for p in passages) / len(passages)
        if all(p["noise"] for p in passages):  # never make a whole document unsearchable
            for passage in passages:
                passage["noise"] = False
        for passage in passages:
            chunks.append({"doc": doc_index, **passage})
        doc["quality"] = data_quality(doc["text"], noise_share, doc["_original"])
        doc["quality_label"] = "High" if doc["quality"] >= 0.75 else "Medium" if doc["quality"] >= 0.5 else "Low"
        doc["n_words"] = len(doc["text"].split())
        doc["n_passages"] = len(passages)
        del doc["text"], doc["_original"]
    n_noise = sum(c["noise"] for c in chunks)
    print(f"Split into {len(chunks)} passages ({n_noise} reference/table passages excluded from search)")

    def heading(chunk):
        doc = documents[chunk["doc"]]
        return doc["title"] + (" - " + chunk["section"] if chunk["section"] else "")

    # --metadata-only refreshes titles/years/quality without recomputing the indexes
    # (only valid while the passages themselves are unchanged).
    metadata_only = "--metadata-only" in sys.argv and (INDEX_DIR / "embeddings.npy").exists()
    if metadata_only:
        vocab = json.loads((INDEX_DIR / "vocab.json").read_text())
        print("Metadata only: keeping the existing BM25 index and embeddings")
    else:
        bm25, vocab = build_bm25([tokenize(heading(c) + " " + c["text"]) for c in chunks])
        sparse.save_npz(INDEX_DIR / "bm25.npz", bm25)
        (INDEX_DIR / "vocab.json").write_text(json.dumps(vocab, ensure_ascii=False))
        print(f"BM25 index: {len(vocab)} terms")
    spelling = build_spelling([heading(c) + " " + c["text"] for c in chunks], vocab)
    (INDEX_DIR / "spelling.json").write_text(json.dumps(spelling, ensure_ascii=False))
    print(f"Spelling suggestions: {len(spelling)} words")
    if not metadata_only:
        from sentence_transformers import CrossEncoder, SentenceTransformer
        # Models are downloaded once into index/; later builds and every search use the local copies.
        if not RERANKER_DIR.exists():
            CrossEncoder(RERANK_MODEL).save(str(RERANKER_DIR))
        if not MODEL_DIR.exists():
            SentenceTransformer(EMBED_MODEL).save(str(MODEL_DIR))
        model = SentenceTransformer(str(MODEL_DIR))
        passages = [f"passage: {heading(c)}\n{c['text']}" for c in chunks]
        embeddings = model.encode(passages, batch_size=64, normalize_embeddings=True,
                                  show_progress_bar=True, convert_to_numpy=True)
        np.save(INDEX_DIR / "embeddings.npy", embeddings.astype(np.float16))

    (INDEX_DIR / "documents.json").write_text(json.dumps(documents, ensure_ascii=False, indent=1))
    with open(INDEX_DIR / "passages.jsonl", "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    info = {"model": EMBED_MODEL, "reranker": RERANK_MODEL, "documents_loaded": n_loaded,
            "documents_indexed": len(documents), "passages": len(chunks), "noise_passages": n_noise,
            "terms": len(vocab), "build_seconds": round(time.time() - start)}
    (INDEX_DIR / "info.json").write_text(json.dumps(info, indent=1))
    print(f"Done in {info['build_seconds']} s -> {INDEX_DIR}")


if __name__ == "__main__":
    main()
