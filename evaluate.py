"""Measure retrieval quality on eval/questions.json for the four search modes.

    python evaluate.py

Metrics (answerable questions):
  * Recall@5  - share of questions with at least one relevant document in the top 5
  * MRR@10    - mean of 1/rank of the first relevant document (0 if not in the top 10)
Metrics (false positives, using the no-answer questions):
  * Without a threshold every mode returns documents for every question, so 100% of the
    no-answer questions get (wrong) results. Each mode's best score is therefore used as a
    confidence value, with a threshold maximising (answered - 0.5 x false positives):
  * Answered  - share of answerable questions whose confidence is above the threshold
  * FP        - share of no-answer questions whose confidence is still above it
  * Separation - probability that a random answerable question scores higher than a random
                no-answer question (ROC AUC; 0.5 = no signal, 1.0 = perfect)
The threshold is fitted on the same questions, so Answered/FP are slightly optimistic.

It also writes index/calibration.json: per mode, the score at the threshold and a spread,
which the search engine turns into the 0-100% match score shown in the app (50% = threshold).
The last row, "rerank + priors", is the app's default ordering (relevance combined with
evidence level, data quality and recency) to check that it does not cost recall.

Writes eval/results.md (summary + per-question misses) and eval/results.json (all details).

    python evaluate.py --heldout eval/heldout.json

scores the app exactly as users see it on questions never used for tuning (nothing is refitted)
and writes eval/heldout_results.md.
"""
import json
import sys
import time

import numpy as np

from common import CALIBRATION_FILE, ROOT
from search import MATCH_THRESHOLD, MODES, SearchEngine

CONFIGS = [(mode, mode, "relevance") for mode in MODES] + [("rerank + priors", "rerank", "best")]

QUESTIONS_FILE = ROOT / "eval" / "questions.json"
RESULTS_MD = ROOT / "eval" / "results.md"
RESULTS_JSON = ROOT / "eval" / "results.json"
K = 5
DEPTH = 10
LANGUAGES = ("en", "fr", "ar", "es")
# Hiding a real answer from a clinician costs more than showing one extra result that the
# app already marks with a low (orange/red) match score, so false positives count half.
FP_WEIGHT = 0.5


def best_threshold(positive: list, negative: list) -> float:
    """Threshold maximising answered rate - FP_WEIGHT * false-positive rate, placed halfway down
    to the next lower observed score so that small score changes do not flip the decision."""
    scores = sorted(set(positive) | set(negative))
    gain = [np.mean(np.array(positive) >= t) - FP_WEIGHT * np.mean(np.array(negative) >= t)
            for t in scores]
    best = int(np.argmax(gain))
    return scores[best] if best == 0 else (scores[best] + scores[best - 1]) / 2


def separation(positive: list, negative: list) -> float:
    """ROC AUC between answerable (positive) and no-answer (negative) confidence scores."""
    pairs = [(p > n) + 0.5 * (p == n) for p in positive for n in negative]
    return float(np.mean(pairs)) if pairs else float("nan")


def run_mode(engine: SearchEngine, questions: list, mode: str, sort: str, alias: dict) -> list:
    rows = []
    for q in questions:
        started = time.perf_counter()
        results = engine.search(q["query"], top_k=DEPTH, mode=mode, sort=sort)
        elapsed_ms = (time.perf_counter() - started) * 1000
        ranked = [r["id"] for r in results]
        relevant = {alias.get(doc_id, doc_id) for doc_id in q["relevant"]}
        rank = next((n for n, doc_id in enumerate(ranked, start=1) if doc_id in relevant), None)
        confidence = max((r["passages"][0]["score"] for r in results), default=float("-inf"))
        rows.append({**q, "mode": mode, "rank": rank, "ms": elapsed_ms, "top5": ranked[:K],
                     "confidence": confidence})
    return rows


def calibration(summary: dict, rows: list) -> dict:
    """Score at the threshold, and a spread so the median answerable question shows ~88%."""
    positive = [r["confidence"] for r in rows if r["relevant"]]
    spread = (float(np.median(positive)) - summary["threshold"]) / 2
    return {"threshold": summary["threshold"], "scale": max(spread, 1e-6)}


def summarize(rows: list) -> dict:
    answerable = [r for r in rows if r["relevant"]]
    no_answer = [r for r in rows if not r["relevant"]]
    positive = [r["confidence"] for r in answerable]
    negative = [r["confidence"] for r in no_answer]
    threshold = best_threshold(positive, negative)
    summary = {
        "recall@5": np.mean([r["rank"] is not None and r["rank"] <= K for r in answerable]),
        "mrr@10": np.mean([1 / r["rank"] if r["rank"] else 0 for r in answerable]),
        "fp_no_threshold": 1.0 if no_answer else float("nan"),
        "threshold": threshold,
        "answered": np.mean([c >= threshold for c in positive]),
        "fp": np.mean([c >= threshold for c in negative]),
        "separation": separation(positive, negative),
        "ms": np.mean([r["ms"] for r in rows]),
    }
    for lang in LANGUAGES:
        subset = [r for r in answerable if r["lang"] == lang]
        summary[f"recall@5_{lang}"] = np.mean([r["rank"] is not None and r["rank"] <= K for r in subset])
        summary[f"n_{lang}"] = len(subset)
    summary["n_answerable"], summary["n_no_answer"] = len(answerable), len(no_answer)
    return {k: float(v) if isinstance(v, (np.floating, float)) else v for k, v in summary.items()}


def markdown_report(summaries: dict, details: dict) -> str:
    s0 = next(iter(summaries.values()))
    lines = [
        "# Evaluation results", "",
        f"{s0['n_answerable']} answerable questions ({', '.join(f'{s0[f'n_{l}']} {l}' for l in LANGUAGES)}) "
        f"and {s0['n_no_answer']} no-answer questions. Generated by `evaluate.py`.", "",
        "| Mode | Recall@5 | MRR@10 | False positives, no threshold | Answered, with threshold | "
        "False positives, with threshold | Separation (AUC) | ms / query |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for mode, s in summaries.items():
        lines.append(f"| {mode} | {s['recall@5']:.0%} | {s['mrr@10']:.2f} | {s['fp_no_threshold']:.0%} | "
                     f"{s['answered']:.0%} | {s['fp']:.0%} | {s['separation']:.2f} | {s['ms']:.0f} |")
    lines += ["", "## Recall@5 by question language", "",
              "| Mode | " + " | ".join(LANGUAGES) + " |", "|---|" + "---|" * len(LANGUAGES)]
    for mode, s in summaries.items():
        lines.append(f"| {mode} | " + " | ".join(f"{s[f'recall@5_{l}']:.0%}" for l in LANGUAGES) + " |")
    for mode in details:
        misses = [r for r in details[mode] if r["relevant"] and (r["rank"] is None or r["rank"] > K)]
        lines += ["", f"## Misses for `{mode}` ({len(misses)})", ""]
        lines += [f"- `{r['id']}` {r['query']} - rank {r['rank'] or '>10'}; top 5: {', '.join(r['top5'])}"
                  for r in misses] or ["- none"]
    return "\n".join(lines) + "\n"


def heldout_check(path) -> None:
    """Score the app exactly as users see it (reranker, best-match order, 50% threshold, current
    calibration) on questions never used for tuning. Nothing is refitted or written to index/."""
    questions = json.loads(path.read_text())["questions"]
    engine = SearchEngine()
    alias = {dup: doc["id"] for doc in engine.documents for dup in doc.get("duplicates", [])}
    engine.search("warm-up query", mode="rerank")
    rows = []
    for q in questions:
        started = time.perf_counter()
        outcome = engine.search_with_suggestion(q["query"], top_k=DEPTH, mode="rerank", sort="best")
        ms = (time.perf_counter() - started) * 1000
        results = outcome["results"]
        relevant = {alias.get(i, i) for i in q["relevant"]}
        shown = [r for r in results if r["match"] >= MATCH_THRESHOLD]
        rank = next((n for n, r in enumerate(results, start=1) if r["id"] in relevant), None)
        rows.append({**q, "ms": ms, "rank": rank, "n_shown": len(shown),
                     "shown_relevant": sum(r["id"] in relevant for r in shown),
                     "corrected": outcome["query"] if outcome["corrected"] else None,
                     "top": [(r["id"], round(r["match"], 2), r["title"][:60]) for r in results[:3]]})

    answerable = [r for r in rows if r["relevant"]]
    no_answer = [r for r in rows if not r["relevant"]]
    share = lambda items, cond: sum(map(cond, items)) / len(items) if items else float("nan")
    shown_total = sum(r["n_shown"] for r in answerable)
    ms = sorted(r["ms"] for r in rows)
    lines = [
        f"# Held-out check ({path.name})", "",
        f"{len(answerable)} answerable and {len(no_answer)} no-answer questions, app settings "
        "(reranker, best-match order, 50% threshold, spelling correction), calibration not refitted.", "",
        "| Measure | Result |", "|---|---|",
        f"| Relevant document in top 5 (Recall@5) | {share(answerable, lambda r: r['rank'] is not None and r['rank'] <= K):.0%} |",
        f"| Answered with a relevant document shown | {share(answerable, lambda r: r['shown_relevant'] > 0):.0%} |",
        f"| Answered, but only wrong documents shown | {share(answerable, lambda r: r['n_shown'] > 0 and r['shown_relevant'] == 0):.0%} |",
        f"| Said 'no confident match' although answer exists | {share(answerable, lambda r: r['n_shown'] == 0):.0%} |",
        f"| No-answer questions with results shown (false alarm) | {share(no_answer, lambda r: r['n_shown'] > 0):.0%} |",
        f"| Shown results that are labelled relevant (lower bound) | {sum(r['shown_relevant'] for r in answerable) / max(shown_total, 1):.0%} |",
        f"| Search time median / slowest | {ms[len(ms) // 2]:.0f} ms / {ms[-1]:.0f} ms |",
        "", "| Kind | Recall@5 | Answered correctly |", "|---|---|---|"]
    for kind in sorted({r["kind"] for r in answerable}):
        subset = [r for r in answerable if r["kind"] == kind]
        lines.append(f"| {kind} ({len(subset)}) | {share(subset, lambda r: r['rank'] is not None and r['rank'] <= K):.0%} | "
                     f"{share(subset, lambda r: r['shown_relevant'] > 0):.0%} |")
    lines += ["", "## Every question", ""]
    for r in rows:
        verdict = ("no-answer: " + ("FALSE ALARM" if r["n_shown"] else "correctly silent")) if not r["relevant"] else \
                  ("OK" if r["shown_relevant"] else "WRONG RESULTS" if r["n_shown"] else "SILENT")
        top = "; ".join(f"{t[1]:.0%} {t[2]}" for t in r["top"])
        fixed = f" (searched as \"{r['corrected']}\")" if r["corrected"] else ""
        lines.append(f"- `{r['id']}` [{r['kind']}] {r['query']}{fixed} -> **{verdict}** "
                     f"(rank {r['rank'] or '>10'}) | {top}")
    report = "\n".join(lines) + "\n"
    (ROOT / "eval" / "heldout_results.md").write_text(report)
    print(report)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--heldout":
        heldout_check(ROOT / sys.argv[2])
        return
    questions = json.loads(QUESTIONS_FILE.read_text())["questions"]
    engine = SearchEngine()
    alias = {dup: doc["id"] for doc in engine.documents for dup in doc.get("duplicates", [])}
    engine.search("warm-up query", mode="rerank")  # load models before timing

    details, summaries = {}, {}
    for name, mode, sort in CONFIGS:
        if sort != "relevance":  # orderings that use the match score need this run's calibration
            fitted = {m: calibration(summaries[m], details[m]) for m in MODES}
            CALIBRATION_FILE.write_text(json.dumps(fitted, indent=1))
            engine.calibration.update(fitted)
        details[name] = run_mode(engine, questions, mode, sort, alias)
        summaries[name] = summarize(details[name])

    report = markdown_report(summaries, details)
    RESULTS_MD.write_text(report)
    RESULTS_JSON.write_text(json.dumps({"summary": summaries, "details": details},
                                       ensure_ascii=False, indent=1, default=str))
    print(report.split("\n## Misses")[0])
    print(f"Full report: {RESULTS_MD}")


if __name__ == "__main__":
    main()
