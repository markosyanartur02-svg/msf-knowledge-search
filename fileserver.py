"""Tiny local file server so a search result opens with one click, without internet.

Serves the 'D4GC data' folder at http://127.0.0.1:8502/ (reachable from this computer only):
  /Original/<id>.pdf|.html   the original document
  /Parsed/<id>.md            the extracted text
  /read/<id>                 reader view: the document's text without menus and banners, in
                             the MSF style (saved web pages look broken offline, this does not)
Pages get a Content-Security-Policy that blocks every external request and script, so opening
one never contacts the internet. Uses the Python standard library plus `markdown`.
"""
import base64
import html
import json
import re
import threading
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import markdown

from common import DATA_DIR, INDEX_DIR, PARSED_DIR, ROOT

FILE_PORT = 8502
OFFLINE_HTML_POLICY = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"
LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic", "es": "Spanish"}

READER_CSS = """
:root {--red: #EE0000; --line: #E2E2E2; --head: "DIN Condensed", "Helvetica Neue Condensed", "Arial Narrow", sans-serif;
       --serif: Georgia, "Iowan Old Style", "Times New Roman", serif; --sans: "Helvetica Neue", Helvetica, Arial, sans-serif;}
body {margin: 0; background: #fff; color: #222; font-family: var(--serif); font-size: 1.08rem; line-height: 1.75;}
header {display: flex; align-items: center; gap: 1.2rem; padding: 1rem 2rem; border-bottom: 1px solid var(--line);}
header img {height: 48px;} header .name {font-family: var(--head); font-weight: 700; font-size: 1.35rem; padding-top: 0.3rem;}
header a {margin-left: auto; font-family: var(--head); font-weight: 700; font-size: 1.05rem; color: #fff; background: var(--red);
          padding: 0.45rem 0.9rem 0.25rem; border-radius: 3px; text-decoration: none;}
main {max-width: 780px; margin: 0 auto; padding: 2rem 1.5rem 4rem;}
.kicker {font-family: var(--sans); font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--red);}
h1 {font-family: var(--head); font-weight: 700; font-size: 2.6rem; line-height: 1.05; color: #000; margin: 0.4rem 0 1.5rem;
    padding-bottom: 1rem; border-bottom: 5px solid var(--red);}
h2, h3, h4 {font-family: var(--head); font-weight: 700; color: #000; line-height: 1.15; margin: 2rem 0 0.6rem;}
h2 {font-size: 1.8rem;} h3 {font-size: 1.45rem;} h4 {font-size: 1.2rem;}
a {color: var(--red);} strong {color: #000;}
table {border-collapse: collapse; width: 100%; margin: 1.2rem 0; font-family: var(--sans); font-size: 0.9rem; line-height: 1.45;}
th, td {border: 1px solid var(--line); padding: 0.45rem 0.6rem; text-align: left; vertical-align: top;}
th {background: #F4F4F4;}
blockquote {border-left: 4px solid var(--red); margin: 1.2rem 0; padding: 0.2rem 1rem; color: #444;}
ul, ol {padding-left: 1.4rem;} li {margin: 0.2rem 0;}
[dir=rtl] th, [dir=rtl] td {text-align: right;} [dir=rtl] ul, [dir=rtl] ol {padding-left: 0; padding-right: 1.4rem;}
"""


@lru_cache(maxsize=1)
def _library():
    documents = {d["id"]: d for d in json.loads((INDEX_DIR / "documents.json").read_text())}
    boilerplate_file = INDEX_DIR / "boilerplate.json"
    boilerplate = set(json.loads(boilerplate_file.read_text())) if boilerplate_file.exists() else set()
    logo = base64.b64encode((ROOT / "assets" / "msf_logo.svg").read_bytes()).decode()
    return documents, boilerplate, logo


def reader_page(doc_id: str):
    """HTML reader view of a document, or None if unknown."""
    documents, boilerplate, logo = _library()
    doc = documents.get(doc_id)
    md_path = PARSED_DIR / f"{doc_id}.md"
    if doc is None or not md_path.exists():
        return None
    lines = [line for line in md_path.read_text(encoding="utf-8", errors="replace").splitlines()
             if line.strip() not in boilerplate]
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", "\n".join(lines))  # images live online, drop them
    body = markdown.markdown(text, extensions=["tables", "sane_lists"])
    rtl = doc["language"] == "ar"
    meta = " · ".join(str(x) for x in (doc["genre"], LANGUAGE_NAMES.get(doc["language"], doc["language"]),
                                       doc.get("year") or "undated") if x)
    title = html.escape(doc["title"])
    return (f'<!doctype html><html lang="{doc["language"]}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>'
            f'<style>{READER_CSS}</style></head><body><header><img src="data:image/svg+xml;base64,{logo}" alt="MSF">'
            f'<span class="name">Field Library</span><a href="/Original/{doc["original_file"]}">Original file</a></header>'
            f'<main{" dir=rtl" if rtl else ""}><div class="kicker">{html.escape(meta)}</div><h1>{title}</h1>{body}</main>'
            f'</body></html>')


class LocalFileHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".md": "text/plain; charset=utf-8", ".html": "text/html; charset=utf-8"}

    def do_GET(self):
        if self.path.startswith("/read/"):
            page = reader_page(self.path[len("/read/"):].split("?")[0])
            if page is None:
                self.send_error(404)
                return
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def end_headers(self):
        path = self.path.lower().split("?")[0]
        if path.endswith((".html", ".htm")) or path.startswith("/read/"):
            self.send_header("Content-Security-Policy", OFFLINE_HTML_POLICY)
        elif path.endswith(".pdf"):  # open in the browser's PDF viewer instead of downloading
            self.send_header("Content-Disposition", "inline")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def list_directory(self, path):  # serve files only, never folder listings
        self.send_error(404)
        return None

    def log_message(self, *args):
        pass


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass  # e.g. the browser closed a PDF before it finished downloading


def start_file_server(port: int = FILE_PORT) -> str:
    """Start the server in a background thread (once) and return its base URL."""
    try:
        server = QuietServer(("127.0.0.1", port), partial(LocalFileHandler, directory=str(DATA_DIR)))
    except OSError:  # already running, e.g. after Streamlit re-ran the script
        return f"http://127.0.0.1:{port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"
