"""
Step 5a - Run the pipeline over the test set and record everything.

This script deliberately records the raw signals (S1, S2, S3, composite,
coverage) for EVERY query, not just the routing outcome. Calibration afterwards
has to sweep candidate thresholds offline; if only the decision at the current
threshold were stored, the threshold could never be re-derived without paying
for another full run.

Hard-routed queries carry no signals by design - nothing is generated for them
(report 4.4) - so they are excluded from threshold calibration and scored
separately on whether hard routing fired at all.

    python eval/run_eval.py            # full set
    python eval/run_eval.py --limit 5  # smoke test
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from pipeline import answer_query  # noqa: E402

TESTSET = ROOT / "eval" / "testset.yaml"
OUT = ROOT / "eval" / "results" / "raw_results.json"


def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    spec = yaml.safe_load(TESTSET.read_text(encoding="utf-8"))
    queries = spec["queries"][:limit] if limit else spec["queries"]

    records: list[dict] = []
    started = time.perf_counter()

    for i, case in enumerate(queries, 1):
        print(f"[{i:>3}/{len(queries)}] {case['id']}  {case['query'][:62]}")
        try:
            # Evaluation traffic must not pollute the operational audit log.
            result = answer_query(case["query"], log=False)
        except Exception as exc:  # noqa: BLE001
            print(f"        ERROR {exc!r}")
            records.append({**case, "error": repr(exc)})
            continue

        signals = result.get("signals") or {}
        records.append(
            {
                "id": case["id"],
                "query": case["query"],
                "category": case["category"],
                "kind": case["kind"],
                "expected_routing": case["expected_routing"],
                "expected_doc_types": case.get("expected_doc_types", []),
                "gold_facts": case.get("gold_facts", []),
                "note": case.get("note", ""),
                "decision": result["decision"],
                "escalate": result["escalate"],
                "reason": result["reason"],
                "answer": result["answer"],
                "draft_answer": result.get("draft_answer", ""),
                "generated": result["generated"],
                "s1": signals.get("s1_retrieval_strength"),
                "s2": signals.get("s2_grounding"),
                "s3": signals.get("s3_self_assessment"),
                "composite": signals.get("composite"),
                "coverage_passed": (result.get("coverage") or {}).get("passed"),
                "coverage_reason": (result.get("coverage") or {}).get("reason"),
                "retrieved_doc_types": result.get("retrieved_doc_types", []),
                "retrieved_chunk_ids": result.get("retrieved_chunk_ids", []),
                "claims": result.get("claims", []),
                "escalation_summary": result.get("escalation_summary"),
                "latency_seconds": result["latency_seconds"],
            }
        )
        print(
            f"        -> {result['decision']}"
            + (f"  C={signals['composite']:.3f}" if signals else "")
            + f"  {result['latency_seconds']:.1f}s"
        )

    elapsed = time.perf_counter() - started
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "query_count": len(records),
                "wall_clock_seconds": round(elapsed, 1),
                "results": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    errors = sum(1 for r in records if "error" in r)
    print(f"\n{len(records)} queries in {elapsed:.0f}s ({errors} errors) -> {OUT}")


if __name__ == "__main__":
    main()
