"""Optional online extras: connection check and AI web search (Google Gemini).

The offline library search never uses this module. The AI search only runs when the computer
is online, a key is configured and the user asks; the question is then sent to Google.
The key (and optionally GEMINI_MODEL) is read from the environment or from the local file
.streamlit/secrets.toml (e.g. GEMINI_API_KEY = "..."), re-read on every request so no restart
is needed. Standard library only (no vendor SDK), so the provider can be swapped in `ask_ai`.
"""
import json
import os
import socket
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

SECRETS_FILE = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
# Google's "latest" aliases follow model updates (fixed names such as gemini-2.5-flash get retired).
# The lite model is the fallback when the main one is overloaded or over quota.
DEFAULT_MODELS = ("gemini-flash-latest", "gemini-flash-lite-latest")
RETRY_CODES = (404, 429, 500, 503)  # model retired, over quota, or busy: try the next option
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CHECK_HOST = ("generativelanguage.googleapis.com", 443)
SYSTEM_PROMPT = (
    "You answer questions from Médecins Sans Frontières (MSF) staff working in humanitarian settings. "
    "Answer concisely and practically, using up-to-date web sources. For clinical questions prefer WHO "
    "and MSF guidance, only give doses that your sources state, and remind the reader to confirm with "
    "MSF clinical guidelines and local protocols.")


def is_online(timeout: float = 1.5) -> bool:
    """True if the AI service can be reached (DNS + TCP connection) within `timeout` seconds."""
    try:
        with socket.create_connection(CHECK_HOST, timeout=timeout):
            return True
    except OSError:
        return False


def _setting(name: str):
    """Environment variable first, then .streamlit/secrets.toml."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8")).get(name) or None
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        return None


def api_key():
    return _setting("GEMINI_API_KEY") or _setting("GOOGLE_API_KEY")


def _generate(key: str, model: str, question: str, web: bool, timeout: float) -> dict:
    body = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}]}
    if web:
        body["tools"] = [{"google_search": {}}]  # ground the answer in a live web search
    request = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": key},
                                     method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    candidate = (data.get("candidates") or [{}])[0]
    answer = "".join(part.get("text", "") for part in candidate.get("content", {}).get("parts", []))
    chunks = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
    sources = [(c["web"].get("title") or c["web"]["uri"], c["web"]["uri"]) for c in chunks if "web" in c]
    return {"answer": answer or "No answer was returned.", "sources": sources, "web": web, "model": model}


def ask_ai(question: str, timeout: float = 45) -> dict:
    """{"answer": markdown, "sources": [(title, url)], "web": searched the web?, "model": name}.
    Tries each model with web search first, then without (web search needs a paid plan on some
    accounts). Raises RuntimeError with a readable message when nothing works."""
    key = api_key()
    if not key:
        raise RuntimeError("AI search needs a Gemini API key: set GEMINI_API_KEY in .streamlit/secrets.toml.")
    models = [m for m in (_setting("GEMINI_MODEL"), *DEFAULT_MODELS) if m]
    last_error = ""
    for web in (True, False):
        for model in dict.fromkeys(models):
            try:
                return _generate(key, model, question, web, timeout)
            except urllib.error.HTTPError as error:
                try:
                    reason = json.loads(error.read()).get("error", {}).get("message", "")
                except ValueError:
                    reason = ""
                last_error = f"Gemini refused the request ({error.code}): {(reason or str(error.reason)).rstrip('.')}."
                if error.code not in RETRY_CODES:  # bad key or bad request: retrying will not help
                    raise RuntimeError(last_error + " Check GEMINI_API_KEY in .streamlit/secrets.toml "
                                                    "(one key, pasted once).")
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                raise RuntimeError(f"Could not reach Gemini: {error}")
    raise RuntimeError(last_error + " The AI service is busy or over its quota; try again later.")
