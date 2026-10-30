"""Bookmarks and search history, stored as small JSON files in user_data/ on this computer."""
import json
import time

from common import USER_DATA_DIR

BOOKMARKS_FILE = USER_DATA_DIR / "bookmarks.json"
HISTORY_FILE = USER_DATA_DIR / "history.json"
HISTORY_LIMIT = 50


def _load(path) -> list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(path, items: list) -> None:
    USER_DATA_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash never leaves a half-written file


def bookmarks() -> list:
    return _load(BOOKMARKS_FILE)


def is_bookmarked(doc_id: str) -> bool:
    return any(b["id"] == doc_id for b in bookmarks())


def toggle_bookmark(doc: dict) -> None:
    items = bookmarks()
    if any(b["id"] == doc["id"] for b in items):
        items = [b for b in items if b["id"] != doc["id"]]
    else:
        keep = ("id", "title", "genre", "language", "year", "original_file", "parsed_file")
        items.insert(0, {**{k: doc.get(k) for k in keep}, "added": time.strftime("%Y-%m-%d %H:%M")})
    _save(BOOKMARKS_FILE, items)


def history() -> list:
    return _load(HISTORY_FILE)


def add_to_history(query: str, n_relevant: int) -> None:
    items = [h for h in history() if h["query"] != query]
    items.insert(0, {"query": query, "relevant": n_relevant, "time": time.strftime("%Y-%m-%d %H:%M")})
    _save(HISTORY_FILE, items[:HISTORY_LIMIT])


def clear_history() -> None:
    _save(HISTORY_FILE, [])
