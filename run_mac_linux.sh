#!/usr/bin/env bash
# MSF Field Library - start script for macOS and Linux.
# First run: creates .venv, installs requirements (needs internet once) and builds the index if it
# is missing. Later runs start the app straight away, fully offline. Open http://localhost:8501
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"

if ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "Python 3.11 or newer is required (found: $("$PY" --version 2>&1)). Install it from python.org."
  exit 1
fi

if [ ! -x .venv/bin/streamlit ]; then
  echo "First run: installing (a few minutes, needs internet once)..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

if [ ! -f index/embeddings.npy ]; then
  echo "Building the search index from 'D4GC data' (downloads the two models once)..."
  .venv/bin/python prep.py
fi

# Headless: no first-run e-mail question; the browser is opened by this script instead.
PORT="${PORT:-8501}"
URL="http://localhost:$PORT"
( sleep 6; open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null ) >/dev/null 2>&1 &
echo "Starting MSF Field Library at $URL (stop with Ctrl+C)"
.venv/bin/streamlit run app.py --server.headless true --server.port "$PORT"
