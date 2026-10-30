"""Hybrid offline search over the index built by prep.py.

A query runs through two retrievers:
  * BM25 keywords  - exact terms such as drug names, acronyms, places;
  * embeddings     - meaning, also across English, French, Arabic and Spanish.
Their rankings are merged with Reciprocal Rank Fusion (RRF). The best candidates are
then re-scored by a small cross-encoder that reads question and passage together, and
passages are grouped per document so each document appears once, with its best passages.

Each result gets a 0-1 match score, calibrated on eval/questions.json by evaluate.py:
0.5 is the confidence threshold (below it the result is probably not relevant).
Results can then be ordered by relevance alone or combined with evidence level
(guideline > research > reports > news > opinion), data quality and recency.

Command line:  python search.py "malaria symptoms"
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never call the internet at query time
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import difflib
import json
import math
import re
import sys
import time

import numpy as np
from scipy import sparse

from common import CALIBRATION_FILE, CURRENT_YEAR, INDEX_DIR, MODEL_DIR, RERANKER_DIR, tokenize

CANDIDATES = 100         # passages taken from each retriever before fusion
PER_LANGUAGE = 25        # best embedding matches added per document language (cross-lingual recall)
RRF_K = 60               # standard RRF constant
RERANK_CANDIDATES = 40   # fused passages re-scored by the cross-encoder
PASSAGES_PER_DOC = 2
# keyword = BM25 only, semantic = embeddings only, hybrid = both fused, rerank = hybrid + cross-encoder
MODES = ("keyword", "semantic", "hybrid", "rerank")
SORTS = {
    "best": "Best match (relevance, evidence, quality, recency)",
    "relevance": "Relevance only",
    "evidence": "Evidence level (guidelines and research first)",
    "quality": "Data quality",
    "newest": "Newest first",
}
# Fallback score calibration (score at the 50% threshold, spread) until evaluate.py writes one.
DEFAULT_CALIBRATION = {"keyword": {"threshold": 12.8, "scale": 6.69},
                       "semantic": {"threshold": 0.8756, "scale": 0.0134},
                       "hybrid": {"threshold": 0.04477, "scale": 0.00187},
                       "rerank": {"threshold": -2.531, "scale": 6.058}}
# Confidence drops when question words never occur in the library ("Lyme", "glaucoma"):
# the score is lowered by this many calibration spreads if all words are unknown.
UNKNOWN_WORDS_PENALTY = 1.3
MATCH_THRESHOLD = 0.5    # results below this match score are treated as not relevant
# "Did you mean": an unknown word is replaced by a library word at least this similar
# (difflib ratio), that occurs at least SPELLING_MIN_COUNT times and starts with the same letter.
# Acronyms (all capitals) and words under 5 letters are never changed, and a suggestion is only
# offered when the results are weak (best match below SUGGEST_BELOW): valid words the library
# does not contain (e.g. many French verbs) are otherwise "corrected" for no reason.
SPELLING_CUTOFF = 0.85   # typos score >= 0.85 ("malria"/"malaria" 0.92); "tennis"/"tens" is 0.80
SPELLING_MIN_COUNT = 3
SUGGEST_BELOW = 0.65
AUTO_CORRECT_MARGIN = 0.05  # the corrected search must be clearly confident to replace the question
_LATIN_WORD = re.compile(r"[a-zà-ÿ'-]{5,}")


def prior(doc: dict) -> float:
    """0-1 trust in a document regardless of the query: evidence level, data quality, recency."""
    if doc.get("year"):
        recency = min(1.0, max(0.0, (doc["year"] - 1990) / (CURRENT_YEAR - 1990)))
    else:
        recency = 1.0 if doc["evidence"] == 5 else 0.5  # undated guideline chapters are living documents
    return 0.5 * doc["evidence"] / 5 + 0.3 * doc["quality"] + 0.2 * recency


def order_results(results: list, sort: str) -> list:
    keys = {
        "best": lambda r: r["match"] * (0.8 + 0.2 * prior(r)),
        "relevance": lambda r: r["match"],
        "evidence": lambda r: (r["evidence"], r["match"]),
        "quality": lambda r: (r["quality"], r["match"]),
        "newest": lambda r: (r.get("year") or 0, r["match"]),
    }
    return sorted(results, key=keys[sort], reverse=True)


class SearchEngine:
    def __init__(self, index_dir=INDEX_DIR):
        from sentence_transformers import CrossEncoder, SentenceTransformer

        self.documents = json.loads((index_dir / "documents.json").read_text())
        with open(index_dir / "passages.jsonl", encoding="utf-8") as f:
            self.passages = [json.loads(line) for line in f]
        self.bm25 = sparse.load_npz(index_dir / "bm25.npz").tocsc()
        self.vocab = json.loads((index_dir / "vocab.json").read_text())
        self.embeddings = np.load(index_dir / "embeddings.npy").astype(np.float32)
        self.model = SentenceTransformer(str(index_dir / MODEL_DIR.name), device="cpu")
        reranker_dir = index_dir / RERANKER_DIR.name
        self.reranker = CrossEncoder(str(reranker_dir), device="cpu") if reranker_dir.exists() else None
        self.passage_doc = np.array([p["doc"] for p in self.passages])
        self.passage_lang = np.array([self.documents[d]["language"] for d in self.passage_doc])
        self.searchable = np.array([not p.get("noise", False) for p in self.passages])
        self.info = json.loads((index_dir / "info.json").read_text())
        self.calibration = dict(DEFAULT_CALIBRATION)
        calibration_file = index_dir / CALIBRATION_FILE.name
        if calibration_file.exists():
            self.calibration.update(json.loads(calibration_file.read_text()))
        spelling_file = index_dir / "spelling.json"
        self.spelling = json.loads(spelling_file.read_text()) if spelling_file.exists() else {}
        self._spelling_by_letter = {}
        for term, (_, count) in self.spelling.items():
            if count >= SPELLING_MIN_COUNT:
                self._spelling_by_letter.setdefault(term[0], []).append(term)

    def match(self, score: float, mode: str) -> float:
        """Raw retriever score -> 0-1 match score; 0.5 at the calibrated confidence threshold."""
        cal = self.calibration[mode]
        z = (score - cal["threshold"]) / cal["scale"]
        return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))

    def _heading(self, idx: int) -> str:
        passage = self.passages[idx]
        title = self.documents[passage["doc"]]["title"]
        return title + (" - " + passage["section"] if passage["section"] else "")

    def unknown_words(self, query: str) -> list:
        """Question words that occur in no document of the library."""
        return [t for t in dict.fromkeys(tokenize(query)) if t not in self.vocab]

    def suggest(self, query: str):
        """Spelling correction from the library's own words ("malria simptoms" -> "malaria symptoms"),
        or None when every word is known or nothing close enough exists."""
        changed = False

        def fix(match):
            nonlocal changed
            word = match.group(0)
            tokens = tokenize(word)
            if (not tokens or tokens[0] in self.vocab or word.isupper()
                    or not _LATIN_WORD.fullmatch(word.lower())):
                return word
            term = tokens[0]
            candidates = [t for t in self._spelling_by_letter.get(term[0], []) if abs(len(t) - len(term)) <= 2]
            close = difflib.get_close_matches(term, candidates, n=3, cutoff=SPELLING_CUTOFF)
            if not close:
                return word
            best = max(close, key=lambda t: (round(difflib.SequenceMatcher(None, term, t).ratio(), 2),
                                             self.spelling[t][1]))
            changed = True
            return self.spelling[best][0]

        corrected = re.sub(r"\w+", fix, query)
        return corrected if changed else None

    def search_with_suggestion(self, query: str, **options) -> dict:
        """Search; if nothing passes the threshold and a spelling correction exists, search the
        corrected question instead (like "Showing results for ..."). Used by the app."""
        results = self.search(query, **options)
        best = max((r["match"] for r in results), default=0.0)
        suggestion = self.suggest(query) if best < SUGGEST_BELOW else None
        if suggestion and best < MATCH_THRESHOLD:
            corrected = self.search(suggestion, **options)
            if any(r["match"] >= MATCH_THRESHOLD + AUTO_CORRECT_MARGIN for r in corrected):
                return {"results": corrected, "query": suggestion, "suggestion": suggestion, "corrected": True}
        return {"results": results, "query": query, "suggestion": suggestion, "corrected": False}

    def _keyword_scores(self, query: str) -> np.ndarray:
        term_ids = sorted({self.vocab[t] for t in tokenize(query) if t in self.vocab})
        if not term_ids:
            return np.zeros(len(self.passages), dtype=np.float32)
        return np.asarray(self.bm25[:, term_ids].sum(axis=1)).ravel()

    def _semantic_scores(self, query: str) -> np.ndarray:
        vector = self.model.encode(f"query: {query}", normalize_embeddings=True)
        return self.embeddings @ vector

    def _allowed_passages(self, languages, genres, min_year) -> np.ndarray:
        allowed = self.searchable.copy()
        if languages:
            ok = np.array([d["language"] in languages for d in self.documents])
            allowed &= ok[self.passage_doc]
        if genres:
            ok = np.array([d["genre"] in genres for d in self.documents])
            allowed &= ok[self.passage_doc]
        if min_year:  # undated documents are kept
            ok = np.array([not d.get("year") or d["year"] >= min_year for d in self.documents])
            allowed &= ok[self.passage_doc]
        return allowed

    def search(self, query: str, top_k: int = 10, languages=None, genres=None, min_year=None,
               mode: str = "rerank", sort: str = "relevance") -> list:
        """Top documents for the query, each with a 0-1 'match' score and its best passages.
        Each passage also carries 'score', the raw score of the chosen mode."""
        if mode not in MODES or sort not in SORTS:
            raise ValueError(f"mode must be one of {MODES}, sort one of {tuple(SORTS)}")
        allowed = self._allowed_passages(languages, genres, min_year)
        keyword = np.where(allowed, self._keyword_scores(query), 0)
        semantic = np.where(allowed, self._semantic_scores(query), -1)

        ranks = {}
        keyword_top = [i for i in np.argsort(-keyword)[:CANDIDATES] if keyword[i] > 0]
        semantic_top = [i for i in np.argsort(-semantic)[:CANDIDATES] if allowed[i]]
        for name, ranking in (("keyword", keyword_top), ("semantic", semantic_top)):
            for rank, idx in enumerate(ranking, start=1):
                ranks.setdefault(idx, {})[name] = rank
        # Embeddings prefer documents in the query's own language, so an Arabic question would
        # never see the English passage that answers it. Add the best matches of every language.
        rankings = [keyword_top, semantic_top]
        for lang in np.unique(self.passage_lang):
            pool = np.where(allowed & (self.passage_lang == lang))[0]
            rankings.append(list(pool[np.argsort(-semantic[pool])[:PER_LANGUAGE]]))

        if mode == "keyword":
            scores = {i: float(keyword[i]) for i in keyword_top}
        elif mode == "semantic":
            scores = {i: float(semantic[i]) for i in semantic_top}
        else:
            scores = {}
            for ranking in rankings:
                for rank, idx in enumerate(ranking, start=1):
                    scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank)
        ordered = sorted(scores, key=scores.get, reverse=True)

        rerank_scores = {}
        if mode == "rerank" and self.reranker is not None and ordered:
            top = ordered[:RERANK_CANDIDATES]
            pairs = [(query, f"{self._heading(i)}. {self.passages[i]['text']}") for i in top]
            rerank_scores = dict(zip(top, self.reranker.predict(pairs, batch_size=32).tolist()))
            ordered = sorted(top, key=rerank_scores.get, reverse=True) + ordered[RERANK_CANDIDATES:]
            # Passages the reranker did not read rank below all that it did, on the same scale.
            floor = min(rerank_scores.values()) - 1.0
            scores = {i: rerank_scores.get(i, floor) for i in ordered}

        # Same shift for every passage of this query: changes the confidence, not the order.
        terms = list(dict.fromkeys(tokenize(query)))
        unknown_share = len(self.unknown_words(query)) / len(terms) if terms else 0.0
        penalty = UNKNOWN_WORDS_PENALTY * DEFAULT_CALIBRATION[mode]["scale"] * unknown_share

        by_doc = {}  # insertion order = rank of each document's best passage
        for idx in ordered:
            hits = by_doc.setdefault(self.passage_doc[idx], [])
            if len(hits) < PASSAGES_PER_DOC:
                passage = self.passages[idx]
                score = scores[idx] - penalty
                hits.append({"section": passage["section"], "text": passage["text"],
                             "score": score, "match": self.match(score, mode),
                             "rerank_score": rerank_scores.get(idx),
                             "similarity": float(semantic[idx]),
                             "keyword_rank": ranks.get(idx, {}).get("keyword"),
                             "semantic_rank": ranks.get(idx, {}).get("semantic")})

        # Take extra documents so re-ordering by evidence/quality/recency has room to act.
        pool = top_k if sort == "relevance" else 2 * top_k
        results = [{**self.documents[doc_index], "passages": hits, "match": hits[0]["match"]}
                   for doc_index, hits in list(by_doc.items())[:pool]]
        return order_results(results, sort)[:top_k]


def make_snippet(text: str, query: str, n_words: int = 60) -> str:
    """Window of the passage covering the most query words, starting at a sentence if possible."""
    words = text.split()
    query_terms = set(tokenize(query))
    matched = [query_terms & set(tokenize(w)) for w in words]
    best_start, best_key = 0, (-1, -1)
    for start in range(0, max(1, len(words) - n_words + 1), 3):
        window = matched[start:start + n_words]
        key = (len(set().union(*window)), sum(bool(m) for m in window))
        if key > best_key:
            best_start, best_key = start, key
    first = next((i for i in range(best_start, len(words)) if matched[i]), best_start)
    start = first
    for i in range(first - 1, max(-1, first - 15), -1):  # back up to the start of the sentence
        if words[i].endswith((".", "!", "?", ":")):
            break
        start = i
    snippet = " ".join(words[start:start + n_words])
    return ("... " if start > 0 else "") + snippet + (" ..." if start + n_words < len(words) else "")


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "malaria symptoms"
    engine = SearchEngine()
    started = time.perf_counter()
    found = engine.search(question)
    print(f'"{question}" -> {len(found)} documents in {(time.perf_counter() - started) * 1000:.0f} ms\n')
    for n, r in enumerate(found, start=1):
        best = r["passages"][0]
        print(f"{n:2d}. {r['title'][:90]}  [{r['genre']}, {r['language']}, {r['original_file']}]")
        rerank = f"{best['rerank_score']:.2f}" if best["rerank_score"] is not None else "-"
        print(f"    match {r['match']:.0%} | section: {best['section'][:70] or '-'} | keyword "
              f"#{best['keyword_rank']} semantic #{best['semantic_rank']} rerank {rerank}")
        print(f"    {make_snippet(best['text'], question, 35)}\n")
