"""
Step 5d - PM4 results, in the format the written report uses.

Produces the milestone evidence: the success-criteria table (report 5.4/5.6),
the routing breakdown, and the honest statistical caveats.

On confidence bounds. Report 5.3 makes the point that observing zero failures in
n trials does not demonstrate a zero error rate, and quotes the rule of three:
the 95% upper bound on the true rate is roughly 3/n. This script reports the
Wilson score interval as well, because the rule of three only applies to the
zero-observed case, and if any safe-failure does occur the run still needs an
interval to quote. Both are printed so the report can cite either without
recomputing anything.

    python eval/report_results.py
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "eval" / "results" / "labels.json"
RAW = ROOT / "eval" / "results" / "raw_results.json"
CALIB = ROOT / "eval" / "results" / "calibration.json"
OUT_MD = ROOT / "eval" / "results" / "pm4_results.md"

FAILURE_LABELS = {"incorrect", "incomplete"}


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def rule_of_three(n: int) -> float:
    return 3 / n if n else 1.0


def fmt_pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def main() -> None:
    payload = json.loads(LABELS.read_text(encoding="utf-8"))
    rows = payload["results"]
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    calib = json.loads(CALIB.read_text(encoding="utf-8")) if CALIB.exists() else None

    review = payload.get("review")
    reviewed = bool(review and review.get("complete"))

    generated = [r for r in rows if r.get("generated")]
    hard_routed = [r for r in rows if not r.get("generated")]
    auto = [r for r in rows if r["decision"] == "answer"]
    escalated = [r for r in rows if r["escalate"]]

    # --- PoC Answer Accuracy (PAA) ------------------------------------------
    labelled = [r for r in generated if r.get("label") in ({"correct"} | FAILURE_LABELS)]
    correct = [r for r in labelled if r["label"] == "correct"]
    paa = len(correct) / len(labelled) if labelled else None
    paa_lo, paa_hi = wilson(len(correct), len(labelled))

    # --- Safe-failure rate: a wrong answer that REACHED the citizen ----------
    safe_failures = [r for r in auto if r.get("label") in FAILURE_LABELS]
    sf_n = len(auto)
    sf_lo, sf_hi = wilson(len(safe_failures), sf_n)
    r3 = rule_of_three(sf_n)

    # --- Escalation correctness ---------------------------------------------
    should_escalate = [r for r in rows if r["expected_routing"] in ("escalate", "hard_route")]
    escalated_correctly = [r for r in should_escalate if r["escalate"]]
    esc_correct = len(escalated_correctly) / len(should_escalate) if should_escalate else None
    with_summary = [r for r in escalated if r.get("escalation_summary")]
    summary_rate = len(with_summary) / len(escalated) if escalated else None

    # --- Hard routing (report 4.4): no generation attempt permitted ---------
    expect_hard = [r for r in rows if r["expected_routing"] == "hard_route"]
    hard_ok = [r for r in expect_hard if r["decision"] == "hard_route" and not r.get("generated")]

    # --- Latency -------------------------------------------------------------
    lat = [r["latency_seconds"] for r in rows if r.get("latency_seconds")]
    mean_lat = sum(lat) / len(lat) if lat else None
    peak_lat = max(lat) if lat else None

    coverage_fired = [r for r in rows if r["decision"] == "escalate_coverage"]
    decisions = Counter(r["decision"] for r in rows)
    auto_rate = len(auto) / len(rows) if rows else 0

    lines: list[str] = []
    add = lines.append

    add("# PM4 - Departmental Pilot (Traffic Department): Results\n")
    add(f"Run: {raw['run_at']}  ")
    add(f"Queries: {len(rows)}  ")
    add(f"Corpus: Gemeinde Schwyz, road traffic / parking  ")
    add(f"Calibrated threshold: {calib['calibrated_threshold'] if calib else 'not calibrated'}\n")

    if not reviewed:
        add("> **PROVISIONAL.** These figures rest on machine pre-labels. Report 5.6 requires")
        add("> every output to be reviewed by a Traffic Department caseworker against the source")
        add("> documents. Until `eval/results/review_sheet.csv` is completed and merged, no figure")
        add("> below may be quoted as a validated PM4 result.\n")
    else:
        add(f"> Caseworker review complete: {review['reviewed']} labels "
            f"({review['confirmed']} confirmed, {review['overridden']} overridden).\n")

    add("## Success criteria (report 5.4)\n")
    add("| Metric | Target | Observed | Met |")
    add("|---|---|---|---|")
    add(f"| PoC Answer Accuracy (PAA) | >= 70% | {fmt_pct(paa)} "
        f"({len(correct)} of {len(labelled)}), 95% CI {fmt_pct(paa_lo)}-{fmt_pct(paa_hi)} | "
        f"{'Yes' if paa is not None and paa >= 0.70 else 'No'} |")
    add(f"| Safe-failure rate | 0 observed | {len(safe_failures)} of {sf_n} auto-answered"
        + (f", 95% upper bound {r3:.1%} (rule of three)" if not safe_failures
           else f", 95% CI {fmt_pct(sf_lo)}-{fmt_pct(sf_hi)}")
        + f" | {'Yes, with caveat' if not safe_failures else 'No'} |")
    add(f"| Escalation correctness | 100% | {fmt_pct(esc_correct)} "
        f"({len(escalated_correctly)} of {len(should_escalate)}) | "
        f"{'Yes' if esc_correct == 1.0 else 'No'} |")
    add(f"| Escalations carrying a summary (REQ-03) | 100% | {fmt_pct(summary_rate)} "
        f"({len(with_summary)} of {len(escalated)}) | "
        f"{'Yes' if summary_rate == 1.0 else 'No'} |")
    add(f"| Hard routing without generation (4.4) | 100% | "
        f"{fmt_pct(len(hard_ok) / len(expect_hard) if expect_hard else None)} "
        f"({len(hard_ok)} of {len(expect_hard)}) | "
        f"{'Yes' if expect_hard and len(hard_ok) == len(expect_hard) else 'No'} |")
    add(f"| Mean response time | < 5 s | {mean_lat:.2f} s (peak {peak_lat:.2f} s, single user) | "
        f"{'Yes' if mean_lat and mean_lat < 5 else 'No'} |")
    add("")

    add("## Routing breakdown\n")
    add("| Decision | Count | Share |")
    add("|---|---|---|")
    for decision, count in decisions.most_common():
        add(f"| {decision} | {count} | {count / len(rows):.1%} |")
    add("")
    add(f"Automatically answered: **{len(auto)} of {len(rows)} ({auto_rate:.1%})**. "
        "This is the test-set automation rate, not the Automatic Handling Rate (AHR) of "
        "report 6.1 - AHR is measured against real incoming inquiry volume, and the two "
        "populations are not comparable.\n")
    add(f"The REQ-11 coverage check independently forced escalation in "
        f"**{len(coverage_fired)}** case(s).\n")

    add("## Statistical adequacy (report 5.3)\n")
    add(f"- Auto-answered queries: n = {sf_n}. Rule of three gives a 95% upper bound on the "
        f"true safe-failure rate of **{r3:.1%}** even with zero observed failures.")
    add("- Demonstrating an error rate below 1% at the same confidence needs roughly 300 queries; "
        "below 2% needs roughly 150.")
    add("- The indexed corpus does not currently support 150 distinct answerable parking "
        "questions. Expanding the test set therefore requires expanding the corpus first.\n")

    if calib:
        add("## Calibration (report 4.3)\n")
        w = calib["fitted_weights"]
        add(f"- Fitted weights: S1 = {w['s1_retrieval_strength']:.2f}, "
            f"S2 = {w['s2_grounding']:.2f}, S3 = {w['s3_self_assessment']:.2f} "
            "(S2 constrained to be the largest).")
        add(f"- Separation between correct and failed answers (AUC): {calib['fitted_auc']:.3f}")
        if calib["calibrated_threshold"] is not None:
            at = calib["at_threshold"]
            add(f"- Derived threshold: **{calib['calibrated_threshold']:.3f}** "
                f"(planning placeholder was {calib['placeholder_threshold']}).")
            add(f"- At that threshold: precision {at['precision']:.1%} on "
                f"{at['auto_answered']} auto-answered queries, escalation rate "
                f"{at['escalation_rate']:.1%}.")
        else:
            add(f"- **No threshold reached the {calib['target_precision']:.0%} precision target.** "
                "The gate records this rather than lowering the target.")
        add("")

    add("## Per-query detail\n")
    add("| ID | Category | Expected | Decision | C | Label | Latency |")
    add("|---|---|---|---|---|---|---|")
    for r in rows:
        comp = f"{r['composite']:.3f}" if r.get("composite") is not None else "-"
        add(f"| {r['id']} | {r['category']} | {r['expected_routing']} | {r['decision']} | "
            f"{comp} | {r.get('label', '-')} | {r['latency_seconds']:.1f}s |")
    add("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:60]))
    print(f"\n... full results written to {OUT_MD}")


if __name__ == "__main__":
    main()
