# MSF Field Library (D4GC 2026 prototype)

Search the Doctors Without Borders document collection with a question such as
"malaria symptoms" and get the relevant passages, a colour-coded match score, and a
one-click link to the original file. After a one-time setup, everything runs on a laptop
CPU with no internet: index, models, document viewer, saved documents and search history.

## Quick start

Requirements: **Python 3.11 or newer** (python.org). Internet is needed once, to install the
Python packages (and, without a pre-built index, to download the two models).

- **macOS / Linux**: run `./run_mac_linux.sh` in a terminal from this folder.
- **Windows**: double-click `run_windows.bat`.

Then open **http://localhost:8501**. The first run installs everything into `.venv` (a few
minutes); later runs start in seconds and work offline.

- The *full* package already contains the data (`D4GC data/`) and the built index with both
  models (`index/`), so nothing is rebuilt.
- The *code-only* package has no data or index: put the `D4GC data` folder (with `Original/` and
  `Parsed/`) next to `app.py`; the start script then builds the index (about 3-10 minutes).
- Optional online AI search: create `.streamlit/secrets.toml` containing
  `GEMINI_API_KEY = "your-key"` (from aistudio.google.com). Never share this file.

Manual steps, if you prefer:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python prep.py          # build ./index (downloads the two models once)
.venv/bin/python evaluate.py      # optional: measure quality and calibrate the match score
.venv/bin/streamlit run app.py    # open http://localhost:8501
```

Command line: `.venv/bin/python search.py "amoxicillin dose for children"`

`prep.py --metadata-only` refreshes titles, years and quality scores in seconds without
recomputing the embeddings.

## Features

- **Hybrid multilingual search**: keywords (BM25) + meaning (embeddings) + a reranker that
  reads the question and passage together. Ask in English, French, Arabic or Spanish and get
  answers from documents in any of these languages.
- **Spelling help**: "malria simptoms" is searched as "malaria symptoms"; a "Did you mean" link
  is offered when results are weak. Built from the library's own words, fully offline.
- **Match score** per result, from red (not relevant) through yellow to green (very relevant).
  50% is the calibrated threshold; below it a result is hidden, and if nothing passes the app
  says "No confident match" instead of guessing.
- **Open files**: one click opens the PDF, or a clean **reader view** for saved web pages
  (MSF-styled text and tables without menus), served by a tiny local file server on 127.0.0.1.
  Nothing is loaded from the internet.
- **Online / offline**: the header shows whether the computer is online. When online, an extra
  **Ask AI** box searches the internet with Google Gemini (with web sources). It needs a key:
  put `GEMINI_API_KEY = "..."` in `.streamlit/secrets.toml` (read on every request, no restart;
  the file is git-ignored, never share it) or `export GEMINI_API_KEY=...` before starting the
  app. Optional `GEMINI_MODEL`; by default `gemini-flash-latest`, then `gemini-flash-lite-latest`, first with Google Search, then without (free API plans may not include web search; the app then says the answer has no sources). Offline, the box is hidden and the library search works as usual; the
  question is only sent to Google when the user asks the AI.
- **Ranking** combines relevance with evidence level (guidelines > research > reports > news >
  opinion), data quality and recency. Documents older than 15 years are flagged; a year filter
  hides them. (`search.py` also offers relevance-only, evidence, quality and newest-first orders.)
- **Saved documents and search history**, stored as JSON in `user_data/` on this computer.
- **MSF look**: white, logo red (#D84434), bold italic wordmark. Place an official logo at
  `assets/msf_logo.png` to show it in the header.

## How it works

| Step | File | What happens |
|---|---|---|
| Build (once, can run at HQ or offline) | `prep.py` | Reads the 582 Markdown files; takes titles and publication years from the original HTML or the first page; drops exact duplicates (e.g. 18 identical msfaccess.org homepage scrapes); removes menu/banner lines repeated across documents; scores data quality (OCR damage, tables, menu pages, scanned PDFs); assigns an evidence level from the document type; splits text into ~150-word passages; flags reference lists and number tables (never in guideline chapters, whose dosing tables matter); builds a spelling word list; a BM25 keyword index and multilingual embeddings. |
| Search (offline) | `search.py` | BM25 (British/American spelling normalised) and embedding search, plus the best matches from each language so cross-language answers are not missed; fused with Reciprocal Rank Fusion; top 40 passages re-scored by a cross-encoder; grouped per document; calibrated 0-100% match score; ordering. |
| Evaluation | `evaluate.py` | 60 labelled field questions (en/fr/ar/es) + 19 questions the collection cannot answer (`eval/questions.json`); Recall@5, MRR@10, answered and false-positive rates; writes `eval/results.md` and the score calibration `index/calibration.json`. |
| App | `app.py` | Streamlit page in MSF style: search box, filters (language, type, year), coloured match scores, file links, saved documents, history. |
| Files | `fileserver.py` | HTTP server for the documents and the reader view, bound to 127.0.0.1. |
| Online extras | `online.py` | Connection check and the optional Gemini web search (standard library only). |
| User data | `library.py` | Bookmarks and history in `user_data/*.json`. |
| Shared | `common.py` | Paths, model names, evidence levels, tokenizer. |

Models (both open source, run on CPU, stored inside `index/` so no internet is needed at query time):
- Embeddings: `intfloat/multilingual-e5-small` (MIT, 118M parameters)
- Reranker: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (118M parameters, multilingual)

Footprint (measured on a laptop CPU): index ~50 MB + models ~930 MB on disk; the running app uses
about 1.9 GB RAM (peak ~2.9 GB while loading); start-up 3.6 s; ~0.7 s per search (median, slowest
~1.1 s). Without the reranker a search takes ~8 ms. Quality and usefulness checks: see
`eval/usefulness.md`.
