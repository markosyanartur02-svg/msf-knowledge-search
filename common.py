"""Shared paths, settings and text helpers for the MSF offline search prototype."""
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "D4GC data"
PARSED_DIR = DATA_DIR / "Parsed"
ORIGINAL_DIR = DATA_DIR / "Original"
METADATA_CSV = ROOT / "documentation.csv"

INDEX_DIR = ROOT / "index"
MODEL_DIR = INDEX_DIR / "model"
RERANKER_DIR = INDEX_DIR / "reranker"
CALIBRATION_FILE = INDEX_DIR / "calibration.json"
USER_DATA_DIR = ROOT / "user_data"   # bookmarks and search history (local JSON files)
CURRENT_YEAR = 2026

# Evidence level per document type (5 = strongest). Used to sort and to slightly favour
# guidance and peer-reviewed research over news, essays and opinion.
EVIDENCE_LEVELS = {
    "Clinical Guideline Chapter": 5,
    "Peer-reviewed Article": 4, "Study Protocol": 4, "Research Governance Document": 4,
    "Research Policy": 4, "Scientific Publication Notice": 4, "Evaluation Report": 4,
    "Evaluation Methodology Guide": 4, "Field Study": 4,
    "Operational Research Essay": 3, "Activity Report Chapter": 3, "Report": 3,
    "Financial Report": 3, "Legal Encyclopedia Entry": 3, "Historical Case Study": 3,
    "Timeline": 3, "Summary": 3,
    "Press Release": 2, "Project Update": 2, "Statement": 2, "Speech": 2, "Interview": 2,
    "Scientific News": 2, "Advocacy Brief": 2,
    "Opinion": 1, "Op-Ed": 1, "Voices from the Field": 1, "First-person Field Account": 1,
    "Critical Essay": 1,
}
EVIDENCE_LABELS = {5: "Clinical guideline", 4: "Research", 3: "Report / reference",
                   2: "News & statements", 1: "Opinion & testimony"}

# Small open multilingual embedding model (MIT licence, 118M parameters, 384 dimensions).
# It maps English, French, Arabic and Spanish text into the same vector space.
EMBED_MODEL = "intfloat/multilingual-e5-small"
# Small multilingual cross-encoder (118M parameters) that re-scores the best candidates by
# reading the question and the passage together.
RERANK_MODEL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"

# Stopwords for English, French and Spanish, written without accents (tokens are accent-stripped).
STOPWORDS = set("""
a an the and or but of to in on at by for with from as is are was were be been being it its this that
these those there their they them he she his her we our you your i not no can could will would may might
also than then so such which who whom what when where how into about after before during between over
under more most other some any all each per has have had do does did if out up very just only
le la les un une des et ou de du au aux en dans par pour sur avec est sont ce ces cet cette qui que
quoi dont ou il elle ils elles on nous vous leur leurs son sa ses se ne pas plus etre ete a
el los las unos unas y o del al es son con por para su sus lo como mas que se este esta estos estas
""".split())

# British spellings mapped to American ones so "haemorrhage" and "hemorrhage" match.
SPELLING_RULES = [
    (re.compile(r"^haem"), "hem"),
    (re.compile(r"^anaem"), "anem"),
    (re.compile(r"^paed"), "ped"),
    (re.compile(r"^oedem"), "edem"),
    (re.compile(r"^oesoph"), "esoph"),
    (re.compile(r"^foet"), "fet"),
    (re.compile(r"^leukaem"), "leukem"),
    (re.compile(r"^diarrhoe"), "diarrhe"),
    (re.compile(r"^gynaec"), "gynec"),
    (re.compile(r"^orthopaed"), "orthoped"),
]

_WORD = re.compile(r"\w+", re.UNICODE)


def strip_accents(text: str) -> str:
    """Remove diacritics so "épidémie" and "epidemie" are the same word."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_token(token: str) -> str:
    """Spelling normalisation plus a very light plural stemmer."""
    for pattern, replacement in SPELLING_RULES:
        token = pattern.sub(replacement, token)
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> list:
    """Lowercase, strip accents, drop stopwords and normalise tokens for keyword search."""
    tokens = []
    for token in _WORD.findall(strip_accents(text.lower())):
        if len(token) < 2 or token in STOPWORDS:
            continue
        tokens.append(normalize_token(token))
    return tokens
