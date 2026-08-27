"""
End-to-end pipeline (report Figure 1).

Order of operations matters and is not arbitrary:

  1. Topic-based hard routing runs FIRST, before retrieval or generation. The
     report requires these inquiries to reach a human "without an automated
     answer attempt" - so the prototype must not generate an answer and then
     discard it. Nothing is generated at all.
  2. Retrieve -> generate -> coverage check -> composite confidence.
  3. Routing decides on coverage and confidence together.
  4. Escalations carry an auto-generated summary (REQ-03).
  5. Every query is written to the pseudonymised audit log (REQ-08/09).

Usage:
    python src/pipeline.py "Was kostet eine Gewerbeparkkarte?"
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auditlog  # noqa: E402
import confidence  # noqa: E402
import coverage as coverage_mod  # noqa: E402
import routing  # noqa: E402
from config import load_config, model_name  # noqa: E402
from generate import generate_answer, generate_summary  # noqa: E402
from retrieve import retrieve  # noqa: E402

CFG = load_config()

NO_ANSWER_TEXT = (
    "Diese Anfrage wird nicht automatisch beantwortet. Sie wurde an die zuständige "
    "Sachbearbeitung der Gemeinde Schwyz weitergeleitet."
)


def answer_query(query: str, *, log: bool = True) -> dict:
    started = time.perf_counter()

    # --- 1. Hard routing, before any generation attempt ----------------------
    hard, matched = routing.is_hard_routed(query)
    if hard:
        route = routing.decide(query, composite=None, coverage=None)
        result = {
            "query": query,
            "answer": NO_ANSWER_TEXT,
            "sources": [],
            "signals": None,
            "coverage": None,
            "decision": route["decision"].value,
            "escalate": True,
            "reason": route["reason"],
            "threshold": route["threshold"],
            "matched_terms": matched,
            "retrieved_chunk_ids": [],
            "retrieved_doc_types": [],
            "generated": False,
        }
        result["escalation_summary"] = generate_summary(query, [], route)
        result["latency_seconds"] = round(time.perf_counter() - started, 3)
        result["model"] = model_name()
        if log:
            auditlog.write(result)
        return result

    # --- 2. Retrieve and generate -------------------------------------------
    hits = retrieve(query)
    generated = generate_answer(query, hits)

    # --- 3. Coverage (REQ-11) and composite confidence (4.3) ----------------
    cov = coverage_mod.check(query, hits)
    signals = confidence.score(
        query, generated["answer"], hits, generated["self_assessment"]
    )

    # --- 4. Route ------------------------------------------------------------
    route = routing.decide(query, signals["composite"], cov)
    escalate = route["escalate"]

    result = {
        "query": query,
        "answer": NO_ANSWER_TEXT if escalate else generated["answer"],
        "draft_answer": generated["answer"],
        "answerable_from_sources": generated["answerable_from_sources"],
        "sources": [
            {
                "chunk_id": h["chunk_id"],
                "doc_title": h["doc_title"],
                "doc_type": h["doc_type"],
                "url": h["source_url"],
                "similarity": round(h["similarity"], 4),
                "cited": h["chunk_id"] in generated["cited_chunk_ids"],
            }
            for h in hits
        ],
        "signals": {k: v for k, v in signals.items() if k != "claims"},
        "claims": signals["claims"],
        "coverage": cov,
        "decision": route["decision"].value,
        "escalate": escalate,
        "reason": route["reason"],
        "threshold": route["threshold"],
        "matched_terms": [],
        "retrieved_chunk_ids": [h["chunk_id"] for h in hits],
        "retrieved_doc_types": sorted({h["doc_type"] for h in hits}),
        "generated": True,
    }

    if escalate:
        result["escalation_summary"] = generate_summary(query, hits, route)

    result["latency_seconds"] = round(time.perf_counter() - started, 3)
    result["model"] = model_name()

    if log:
        auditlog.write(result)
    return result


def _print(result: dict) -> None:
    print(f"\nFrage:      {result['query']}")
    print(f"Entscheid:  {result['decision']}")
    print(f"Begründung: {result['reason']}")
    if result["signals"]:
        s = result["signals"]
        print(
            f"Signale:    S1={s['s1_retrieval_strength']:.3f} "
            f"S2={s['s2_grounding']:.3f} S3={s['s3_self_assessment']:.3f} "
            f"-> C={s['composite']:.3f} (Schwelle {result['threshold']:.3f})"
        )
    if result.get("coverage"):
        print(f"Deckung:    {result['coverage']['reason']}")
    print(f"Latenz:     {result['latency_seconds']:.2f}s")
    print(f"\nAntwort:\n{result['answer']}")

    if result.get("escalation_summary"):
        summary = result["escalation_summary"]
        print("\n--- Eskalation an die Sachbearbeitung (REQ-03) ---")
        print(f"Betreff:  {summary['betreff']}")
        print(f"Anliegen: {summary['anliegen']}")
        print(f"Grund:    {summary['eskalationsgrund']}")
        for point in summary.get("offene_punkte", []):
            print(f"  - {point}")

    if result["sources"]:
        print("\nQuellen:")
        for src in result["sources"]:
            mark = "*" if src["cited"] else " "
            print(
                f" {mark} {src['similarity']:.3f} [{src['doc_type']}] "
                f"{src['doc_title']}\n     {src['url']}"
            )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python src/pipeline.py "Ihre Frage"  [--json]')
    as_json = "--json" in sys.argv
    query = " ".join(a for a in sys.argv[1:] if a != "--json")
    result = answer_query(query)
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print(result)


if __name__ == "__main__":
    main()
