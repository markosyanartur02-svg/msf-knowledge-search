"""Streamlit app for the MSF offline search.  Run:  streamlit run app.py

Everything runs on this computer: the search index, the models, the file server that opens
original documents (fileserver.py) and the saved documents / search history (library.py).
Styled after msf-azg.be / msf.org: official MSF logo (assets/msf_logo.svg, taken from the
saved msf.org pages in the dataset), MSF red #EE0000, condensed bold headings, serif text.
Only fonts installed on the computer are used, so nothing is loaded from the internet.
"""
import base64
import html
import re
import time

import streamlit as st

import library
from common import CURRENT_YEAR, ROOT, tokenize
from fileserver import start_file_server
from online import ask_ai, is_online
from search import MATCH_THRESHOLD, SearchEngine, make_snippet

LANGUAGE_NAMES = {"en": "English", "fr": "French", "ar": "Arabic", "es": "Spanish"}
OLD_AFTER_YEARS = 15     # documents older than this get an "older document" warning
YEAR_FILTERS = {"Any year": None, "2000 or later": 2000, "2010 or later": 2010,
                "2015 or later": 2015, "2020 or later": 2020}
TOP_K = 10               # documents retrieved per search
EXAMPLES = ["malaria symptoms", "amoxicilline enfant", "علاج الكوليرا", "MDR-TB"]
LOGO_FILE = ROOT / "assets" / "msf_logo.svg"

st.set_page_config(page_title="MSF Field Library", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
:root {--msf-red: #EE0000; --msf-red-dark: #C40000; --ink: #000; --text: #222; --muted: #666; --line: #E2E2E2;
       --head: "DIN Condensed", "Helvetica Neue Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
       --sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
       --serif: Georgia, "Iowan Old Style", "Times New Roman", serif;}
.stApp {background: #fff;}
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], #MainMenu, footer {display: none !important;}
.block-container, [data-testid="stMainBlockContainer"] {padding-top: 0; max-width: 1240px;}

/* top bar */
.msf-top {display: flex; align-items: center; gap: 2rem; padding: 1.4rem 0 1.2rem 0;
          border-bottom: 1px solid var(--line); margin-bottom: 2.4rem;}
.msf-top img {height: 62px;}
.msf-top .product {font-family: var(--head); font-weight: 700; font-size: 1.55rem; color: var(--ink);
                   letter-spacing: 0.01em; padding-top: 0.35rem;}
.msf-top .right {margin-left: auto; display: flex; align-items: center; gap: 1.4rem;}
.msf-top .sections {font-family: var(--head); font-weight: 700; font-size: 1.2rem; color: var(--ink); padding-top: 0.3rem;}
.status {display: flex; align-items: center; gap: 0.45rem; font-family: var(--head); font-weight: 700; font-size: 1.15rem;
          padding: 0.5rem 0.95rem 0.3rem 0.85rem; border-radius: 3px; border: 1.5px solid;}
.status i {width: 0.6rem; height: 0.6rem; border-radius: 50%; display: inline-block; margin-bottom: 0.2rem;}
.status.on {color: #13803B; border-color: #13803B;} .status.on i {background: #1DB954;}
.status.off {color: #666; border-color: #999;} .status.off i {background: #999;}
.st-key-ai-box {border: 1px solid var(--line); border-left: 5px solid #000; padding: 1rem 1.2rem 0.6rem 1.2rem;
                margin-top: 0.4rem; background: #FAFAFA;}
.ai-title {font-family: var(--head); font-weight: 700; font-size: 1.5rem; color: #000;}
.ai-tag {font-family: var(--sans); font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: #fff;
         background: #13803B; border-radius: 999px; padding: 0.1rem 0.5rem; vertical-align: 4px; margin-left: 0.3rem;}
.ai-note {font-family: var(--sans); font-size: 0.82rem; color: var(--muted); margin-top: 0.1rem;}
.st-key-ai-box [data-testid="stBaseButton-primary"] {background: #000; border-color: #000;}
.st-key-ai-box [data-testid="stBaseButton-primary"]:hover {background: #333; border-color: #333;}
.st-key-ai-answer {background: #fff; border: 1px solid var(--line); padding: 0.9rem 1.1rem; font-family: var(--serif);}
.st-key-ai-answer a {color: var(--msf-red);}
.st-key-ai-answer h1, .st-key-ai-answer h2, .st-key-ai-answer h3, .st-key-ai-answer h4 {
    font-family: var(--head); font-size: 1.25rem !important; line-height: 1.2; margin: 0.8rem 0 0.3rem; padding: 0;}
.ai-warning {font-family: var(--sans); font-size: 0.82rem; color: #7A4B00; background: #FFF6E0;
             border-left: 4px solid #E0A100; padding: 0.45rem 0.7rem;}
.msf-top .pill {background: var(--msf-red); color: #fff; font-family: var(--head); font-weight: 700;
                font-size: 1.15rem; padding: 0.55rem 1.1rem 0.35rem 1.1rem; border-radius: 3px;}

/* hero */
.hero-title {font-family: var(--head); font-weight: 700; color: var(--ink); font-size: 3.6rem;
             line-height: 1.02; margin: 0.4rem 0 1.1rem 0; letter-spacing: 0.005em;}
.hero-text {font-family: var(--serif); font-size: 1.12rem; line-height: 1.85; color: var(--text); margin-bottom: 1.3rem;}
.hero-text a, .hero-text .red {color: var(--msf-red); text-decoration: none;}
.try {font-family: var(--sans); font-size: 0.9rem; color: var(--muted); margin: 0.2rem 0 0.4rem 0;}

/* inputs and buttons */
[data-testid="stTextInputRootElement"] {background: #fff; border: 1.5px solid #000; border-radius: 3px; min-height: 3.35rem;}
[data-testid="stTextInputRootElement"]:focus-within {border-color: var(--msf-red);}
.stTextInput input {font-family: var(--sans); font-size: 1.1rem; padding: 0.85rem 1rem; background: #fff; color: #000;}
.stButton button, .stButton button p {font-family: var(--head); font-weight: 700; font-size: 1.15rem;}
.stButton button {border-radius: 3px; padding-top: 0.5rem;}
[data-testid="stBaseButton-primary"] {background: var(--msf-red); border: 1.5px solid var(--msf-red); color: #fff; min-height: 3.35rem;}
[data-testid="stBaseButton-primary"]:hover {background: var(--msf-red-dark); border-color: var(--msf-red-dark); color: #fff;}
[data-testid="stBaseButton-secondary"] {background: #fff; border: 1.5px solid var(--msf-red); color: var(--msf-red);}
[data-testid="stBaseButton-secondary"]:hover {background: var(--msf-red); color: #fff; border-color: var(--msf-red);}
[data-testid="stExpander"] details {border: 1px solid var(--line); border-radius: 3px;}
[data-testid="stExpander"] summary p {font-family: var(--head); font-weight: 700; font-size: 1.1rem;}

/* quiet side card (recent searches + saved documents) */
.st-key-panel {background: #FAFAFA; border: 1px solid var(--line); border-top: 4px solid var(--msf-red);
               padding: 1.5rem 1.6rem 1.3rem 1.6rem; gap: 0.9rem; margin-top: 0.6rem;}
.st-key-panel .panel-title {font-family: var(--head); font-weight: 700; color: #000; font-size: 1.3rem;
                            letter-spacing: 0.01em; line-height: 1.2; margin: 0; padding-top: 0.15rem;}
.st-key-panel .panel-title .count {display: inline-block; font-family: var(--sans); font-size: 0.72rem; font-weight: 700;
    color: #fff; background: var(--msf-red); border-radius: 999px; padding: 0.1rem 0.5rem; margin-left: 0.5rem;
    vertical-align: 4px;}
.st-key-panel .panel-note {font-family: var(--sans); color: var(--muted); font-size: 0.85rem; line-height: 1.5;}
.st-key-panel .panel-divider {border-top: 1px solid var(--line); margin: 0.35rem 0 0.25rem 0;}
.st-key-recent {gap: 0.55rem !important;}
.st-key-recent [data-testid="stBaseButton-secondary"] {background: #fff; border: 1px solid #D5D5D5; color: #000;
    min-height: 2.1rem; padding: 0.25rem 0.95rem; border-radius: 999px;}
.st-key-recent [data-testid="stBaseButton-secondary"] p {font-family: var(--sans); font-weight: 500; font-size: 0.86rem;}
.st-key-recent [data-testid="stBaseButton-secondary"]:hover {border-color: var(--msf-red); color: var(--msf-red); background: #fff;}
.st-key-panel [data-testid="stBaseButton-tertiary"], .st-key-panel [data-testid="stBaseButton-tertiary"] p {
    color: var(--muted); font-family: var(--sans); font-size: 0.85rem; font-weight: 400; min-height: 0; padding: 0.1rem 0.25rem;}
.st-key-panel [data-testid="stBaseButton-tertiary"]:hover, .st-key-panel [data-testid="stBaseButton-tertiary"]:hover p {color: var(--msf-red);}
[class*="st-key-saved-"] {background: #fff; border: 1px solid var(--line); border-left: 3px solid var(--msf-red);
                          padding: 0.6rem 0.4rem 0.6rem 0.85rem;}
.saved-link {display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
             font-family: var(--sans); font-size: 0.92rem; font-weight: 700; color: #000 !important;
             line-height: 1.35; text-decoration: none !important;}
.st-key-clear-wrap {padding-top: 0.3rem;}
.saved-link:hover {color: var(--msf-red) !important;}
.saved-meta {font-family: var(--sans); font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem;}
.st-key-examples [data-testid="stBaseButton-secondary"] {min-height: 0; padding: 0.3rem 0.85rem;}

/* full-width red band */
.band {background: var(--msf-red); margin: 2.6rem calc(50% - 50vw) 1.8rem calc(50% - 50vw);
       padding: 2.1rem calc(50vw - 50% + 1rem) 1.7rem calc(50vw - 50% + 1rem);}
.band h2 {font-family: var(--head); font-weight: 700; color: #fff; font-size: 2.9rem; margin: 0; padding: 0; line-height: 1.05;}
.band .sub {font-family: var(--sans); color: #fff; opacity: 0.92; font-size: 1rem; margin-top: 0.3rem;}

/* results */
.result-title {font-family: var(--head); font-weight: 700; font-size: 1.75rem; line-height: 1.12; margin-top: 0.3rem;}
.result-title a {color: var(--ink); text-decoration: none;}
.result-title a:hover {color: var(--msf-red);}
.score {display: inline-block; font-family: var(--sans); min-width: 3.3rem; text-align: center; color: #fff;
        font-weight: 800; border-radius: 999px; padding: 0.12rem 0.5rem; margin-right: 0.55rem;
        font-size: 0.85rem; vertical-align: 5px;}
.meta {font-family: var(--sans); font-size: 0.86rem; color: var(--muted); margin-top: 0.35rem;}
.chip {display: inline-block; border: 1px solid #000; border-radius: 2px; padding: 0 0.4rem; margin-right: 0.3rem;
       font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em; color: #000;}
.warn {color: var(--msf-red); font-weight: 700;}
.passage {font-family: var(--serif); line-height: 1.8; font-size: 1.05rem; color: var(--text); margin: 0.6rem 0 0.5rem 0;}
.passage[dir=rtl] {text-align: right; font-family: var(--sans);}
mark {background: transparent; color: var(--msf-red); font-weight: 700; padding: 0;}
.links {font-family: var(--head); font-weight: 700; font-size: 1.15rem; margin: 0.2rem 0 0.4rem 0;}
.links a {color: var(--msf-red); text-decoration: none; margin-right: 1.4rem;}
.links a:hover {text-decoration: underline;}
.spelling {font-family: var(--serif); font-size: 1.05rem; color: var(--text); margin: -0.6rem 0 0.8rem 0;}
.spelling b {color: var(--msf-red);}
.st-key-did-you-mean {margin: -0.6rem 0 0.8rem 0; gap: 0.4rem;}
.st-key-did-you-mean .spelling {margin: 0;}
.st-key-did-you-mean [data-testid="stBaseButton-tertiary"], .st-key-did-you-mean [data-testid="stBaseButton-tertiary"] p {
    color: var(--msf-red); font-family: var(--serif); font-size: 1.05rem; font-weight: 700; font-style: italic;
    text-decoration: underline; padding: 0; min-height: 0;}
.notice {border-left: 6px solid var(--msf-red); background: #FFF1F1; padding: 1rem 1.2rem;
         font-family: var(--serif); font-size: 1.05rem; color: var(--text); margin-bottom: 1rem;}
hr {border-color: var(--line);}
</style>""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading the library...")
def load_engine() -> SearchEngine:
    return SearchEngine()


@st.cache_resource
def file_server_url() -> str:
    return start_file_server()


@st.cache_data(ttl=20, show_spinner=False)
def connection_status() -> bool:
    """Checked at most every 20 s; offline is detected in about 1.5 s at worst."""
    return is_online()


def status_pill(online: bool) -> str:
    if online:
        return '<div class="status on" title="Internet available: AI web search enabled"><i></i>Online</div>'
    return '<div class="status off" title="No internet connection. Library search remains available."><i></i>Offline</div>'


@st.cache_data
def logo_data_uri() -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(LOGO_FILE.read_bytes()).decode()


def score_color(match: float) -> str:
    """Red (0%) through orange and yellow to green (100%)."""
    return f"hsl({int(120 * max(0.0, min(1.0, match)))}, 68%, 38%)"


def match_label(match: float) -> str:
    return "High match" if match >= 0.75 else "Medium match" if match >= MATCH_THRESHOLD else "Low match"


def highlight(text: str, query: str) -> str:
    """HTML-escape the passage and mark the words that match the query."""
    terms = set(tokenize(query))

    def mark(m):
        return f"<mark>{m.group(0)}</mark>" if terms & set(tokenize(m.group(0))) else m.group(0)

    return re.sub(r"\w+", mark, html.escape(text))


def passage_html(text: str, query: str, language: str) -> str:
    direction = "rtl" if language == "ar" else "ltr"
    return f'<div class="passage" dir="{direction}">{highlight(text, query)}</div>'


def use_query(query: str) -> None:
    st.session_state.query = query


def open_url(doc: dict, base_url: str) -> str:
    """PDFs open as they are; saved web pages open in the clean reader view."""
    if doc["original_file"].endswith(".pdf"):
        return f'{base_url}/Original/{doc["original_file"]}'
    return f'{base_url}/read/{doc["id"]}'


def render_result(r: dict, query: str, base_url: str) -> None:
    best = r["passages"][0]
    original = f'{base_url}/Original/{r["original_file"]}'
    reader = f'{base_url}/read/{r["id"]}'
    title_col, button_col = st.columns([0.86, 0.14])
    with title_col:
        st.markdown(
            f'<div class="result-title"><span class="score" style="background:{score_color(r["match"])}" '
            f'title="{match_label(r["match"])}">{r["match"]:.0%}</span>'
            f'<a href="{open_url(r, base_url)}" target="_blank">{html.escape(r["title"])}</a></div>',
            unsafe_allow_html=True)
    with button_col:
        saved = library.is_bookmarked(r["id"])
        st.button("★ Saved" if saved else "☆ Save", key=f"bookmark-{r['id']}",
                  on_click=library.toggle_bookmark, args=(r,), width="stretch")

    year = r.get("year")
    if year and year < CURRENT_YEAR - OLD_AFTER_YEARS:
        year_html = f'<span class="warn" title="Check for newer guidance">{year} · older document</span>'
    else:
        year_html = str(year) if year else "undated"
    section = f' · <i>{html.escape(best["section"])}</i>' if best["section"] else ""
    st.markdown(
        f'<div class="meta"><span class="chip">{r["evidence_label"]}</span>'
        f'<span class="chip">Data quality: {r["quality_label"]}</span> {html.escape(r["genre"])} · '
        f'{LANGUAGE_NAMES.get(r["language"], r["language"])} · {year_html}{section}</div>',
        unsafe_allow_html=True)
    st.markdown(passage_html(make_snippet(best["text"], query), query, r["language"]), unsafe_allow_html=True)
    if r["original_file"].endswith(".pdf"):
        links = (f'<a href="{original}" target="_blank">Open PDF →</a>'
                 f'<a href="{reader}" target="_blank">Read as text →</a>')
    else:
        links = (f'<a href="{reader}" target="_blank">Read document →</a>'
                 f'<a href="{original}" target="_blank">Original web page →</a>')
    st.markdown(f'<div class="links">{links}</div>', unsafe_allow_html=True)
    with st.expander("More from this document"):
        for passage in r["passages"]:
            st.caption(f"{passage['section'] or 'Passage'} · match {passage['match']:.0%}")
            st.markdown(passage_html(passage["text"], query, r["language"]), unsafe_allow_html=True)
        if r.get("duplicates"):
            st.caption("Identical copies in the collection: " + ", ".join(r["duplicates"]))
    st.divider()


engine = load_engine()
base_url = file_server_url()

# Search first (widget values are already in session state) so the history panel is up to date.
query = st.session_state.get("query", "").strip()
languages = st.session_state.get("filter-language", [])
genres = st.session_state.get("filter-type", [])
min_year = YEAR_FILTERS[st.session_state.get("filter-year", "Any year")]
if query:
    started = time.perf_counter()
    outcome = engine.search_with_suggestion(query, top_k=TOP_K, languages=languages, genres=genres,
                                            min_year=min_year, sort="best",
                                            mode="rerank" if engine.reranker is not None else "hybrid")
    elapsed = time.perf_counter() - started
    results, searched = outcome["results"], outcome["query"]
    relevant = [r for r in results if r["match"] >= MATCH_THRESHOLD]
    weak = [r for r in results if r["match"] < MATCH_THRESHOLD]
    if st.session_state.get("last_logged") != query:
        library.add_to_history(query, len(relevant))
        st.session_state.last_logged = query

# ---------------------------------------------------------------- top bar
online = connection_status()
st.markdown(
    f'<div class="msf-top"><img src="{logo_data_uri()}" alt="Médecins Sans Frontières">'
    f'<div class="product">Knowledge Search</div><div class="right"><div class="sections">Guidelines · Research · Field reports</div>'
    f'{status_pill(online)}</div></div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- hero: search + red panel
left, right = st.columns([0.6, 0.4], gap="large")
with left:
    st.markdown('<div class="hero-title">Evidence and guidance<br>for MSF field teams</div>'
                '<div class="hero-text">Search <span class="red">the Médecins Sans Frontières document library</span>: '
                'clinical guidelines, peer-reviewed research, operational reports and field updates. Results are '
                'ranked by relevance, with the strongest evidence and most recent guidance first.</div>',
                unsafe_allow_html=True)
    box, button = st.columns([0.76, 0.24])
    with box:
        st.text_input("Search the library", key="query", label_visibility="collapsed",
                      placeholder="Question, condition or drug")
    with button:
        st.button("Search  →", type="primary", width="stretch")
    st.markdown('<div class="try">Examples</div>', unsafe_allow_html=True)
    with st.container(horizontal=True, wrap=True, gap="small", key="examples"):
        for example in EXAMPLES:
            st.button(example, key=f"example-{example}", on_click=use_query, args=(example,))
    with st.expander("Filters: language, document type, year"):
        f1, f2, f3 = st.columns(3)
        f1.multiselect("Language", sorted({d["language"] for d in engine.documents}), key="filter-language",
                       format_func=lambda code: LANGUAGE_NAMES.get(code, code))
        f2.multiselect("Document type", sorted({d["genre"] for d in engine.documents}), key="filter-type")
        f3.selectbox("Published", list(YEAR_FILTERS), key="filter-year")

    # Online only: a second search box that asks an AI with live web search (Google Gemini).
    if online:
        with st.container(key="ai-box"):
            st.markdown('<div class="ai-title">Ask AI <span class="ai-tag">online</span></div>'
                        '<div class="ai-note">Answers generated by Google Gemini. Queries are sent to Google; '
                        'verify clinical information against MSF guidelines.</div>', unsafe_allow_html=True)
            ai_box, ai_button = st.columns([0.76, 0.24])
            with ai_box:
                ai_query = st.text_input("Ask AI", key="ai_query", label_visibility="collapsed",
                                         placeholder="e.g. latest WHO guidance on mpox vaccination").strip()
            with ai_button:
                st.button("Ask AI  →", key="ask-ai", type="primary", width="stretch")
            if ai_query:
                answers = st.session_state.setdefault("ai_answers", {})
                if ai_query not in answers:  # one call per question, not one per rerun
                    with st.spinner("Searching the internet..."):
                        try:
                            answers[ai_query] = ask_ai(ai_query)
                        except RuntimeError as error:
                            answers[ai_query] = {"error": str(error)}
                reply = answers[ai_query]
                if "error" in reply:
                    st.markdown(f'<div class="notice">{html.escape(reply["error"])}</div>', unsafe_allow_html=True)
                    answers.pop(ai_query)  # only answers are kept; a fixed key or connection works next time
                else:
                    with st.container(key="ai-answer"):
                        if not reply["web"]:
                            st.markdown('<div class="ai-warning">Web search is not available on this API plan: '
                                        'this answer comes from the AI model\'s own knowledge, without sources, '
                                        'and may be out of date.</div>', unsafe_allow_html=True)
                        st.markdown(reply["answer"])
                        st.caption(f"Answered by {reply['model']}" + (" with Google Search" if reply["web"] else ""))
                        if reply["sources"]:
                            st.markdown("**Sources:** " + " · ".join(
                                f'<a href="{html.escape(url)}" target="_blank">{html.escape(title)}</a>'
                                for title, url in reply["sources"][:6]), unsafe_allow_html=True)

with right:
    with st.container(key="panel"):
        past = library.history()
        title_col, clear_col = st.columns([0.7, 0.3], vertical_alignment="center")
        title_col.markdown('<div class="panel-title">Recent searches</div>', unsafe_allow_html=True)
        if past:
            with clear_col.container(horizontal=True, horizontal_alignment="right", key="clear-wrap"):
                st.button("Clear", key="clear-history", type="tertiary", on_click=library.clear_history)
        if not past:
            st.markdown('<div class="panel-note">Your searches will appear here.</div>', unsafe_allow_html=True)
        else:
            with st.container(horizontal=True, wrap=True, gap="small", key="recent"):
                for i, h in enumerate(past[:6]):
                    label = h["query"] if len(h["query"]) <= 28 else h["query"][:27] + "…"
                    st.button(label, key=f"history-{i}", on_click=use_query, args=(h["query"],))

        st.markdown('<div class="panel-divider"></div>', unsafe_allow_html=True)

        saved = library.bookmarks()
        st.markdown(f'<div class="panel-title">Saved documents<span class="count">{len(saved)}</span></div>',
                    unsafe_allow_html=True)
        if not saved:
            st.markdown('<div class="panel-note">Use ☆ Save next to a result to keep it here.</div>',
                        unsafe_allow_html=True)
        for b in saved[:4]:
            with st.container(key=f"saved-{b['id']}"):
                link_col, remove_col = st.columns([0.88, 0.12], vertical_alignment="center")
                link_col.markdown(
                    f'<a class="saved-link" href="{open_url(b, base_url)}" target="_blank" '
                    f'title="{html.escape(b["title"])}">{html.escape(b["title"])}</a>'
                    f'<div class="saved-meta">{html.escape(b["genre"])} · {b.get("year") or "undated"}</div>',
                    unsafe_allow_html=True)
                remove_col.button("✕", key=f"unsave-{b['id']}", type="tertiary", help="Remove from saved",
                                  on_click=library.toggle_bookmark, args=(b,))
        if len(saved) > 4:
            st.markdown(f'<div class="panel-note">and {len(saved) - 4} more</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- results
if query:
    count = f"{len(relevant)} relevant documents" if relevant else "No confident match"
    st.markdown(f'<div class="band"><h2>Results for “{html.escape(searched)}”</h2>'
                f'<div class="sub">{count} · {elapsed:.1f} s</div></div>',
                unsafe_allow_html=True)
    if outcome["corrected"]:
        st.markdown(f'<div class="spelling">No confident match for “{html.escape(query)}”. '
                    f'Showing results for <b>{html.escape(searched)}</b>.</div>', unsafe_allow_html=True)
    elif outcome["suggestion"]:
        with st.container(horizontal=True, vertical_alignment="center", key="did-you-mean"):
            st.markdown('<div class="spelling">Did you mean:</div>', unsafe_allow_html=True)
            st.button(outcome["suggestion"], key="suggestion", type="tertiary",
                      on_click=use_query, args=(outcome["suggestion"],))
    if not relevant:
        unknown = engine.unknown_words(searched)
        hint = (f" These words appear in no document of the library: <b>{html.escape(', '.join(unknown))}</b>."
                if unknown else "")
        st.markdown(f'<div class="notice"><b>No confident match.</b> The library does not seem to answer this '
                    f'question.{hint} Try other words, another language, or fewer filters.</div>',
                    unsafe_allow_html=True)
    for result in relevant:
        render_result(result, searched, base_url)
    if weak and st.toggle(f"Show {len(weak)} less relevant documents", value=False):
        for result in weak:
            render_result(result, searched, base_url)
