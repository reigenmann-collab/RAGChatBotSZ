"""
Step 5c - Weight fitting and threshold calibration (report 4.3).

The report is emphatic that the threshold is DERIVED, not chosen, and that the
85% figure from earlier planning documents was a placeholder used to size the
escalation workload rather than a calibrated value. This script implements the
four-step procedure verbatim:

  1. Every test query is answered by the pipeline and independently labelled
     correct / incorrect / incomplete (eval/label.py).
  2. The composite score C is computed for each query and its distribution is
     plotted separately for correct and for incorrect-or-incomplete answers.
  3. Precision on auto-answered queries is plotted as a function of the
     threshold, together with the resulting escalation rate.
  4. The threshold is set at the LOWEST value at which precision on
     auto-answered queries meets the safety target, and the corresponding
     escalation rate is reported as the operational cost of that safety level.

Weights are fitted here too, subject to the report's structural constraint that
S2 (grounding) carries the largest weight, because grounding failure is the
failure mode with the most serious consequence for a public authority.

Two modelling decisions worth stating plainly:

  - "incomplete" counts as a FAILURE, not a partial success. The PoC's own
    limitation was two answers that were correct but incomplete, and treating
    them as successes here would calibrate the threshold against the very
    failure mode the exercise exists to catch.
  - The coverage check is applied at every candidate threshold but is never
    part of C. It is an independent trigger (report 4.3), so a query failing
    coverage is escalated regardless of where the threshold sits.

    python eval/calibrate.py            # fit, plot, write calibration.json
    python eval/calibrate.py --apply    # additionally write the threshold into config.yaml
"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "eval" / "results" / "labels.json"
OUT = ROOT / "eval" / "results" / "calibration.json"
FIG_DIR = ROOT / "eval" / "results"

FAILURE_LABELS = {"incorrect", "incomplete"}


def load_rows() -> list[dict]:
    payload = json.loads(LABELS.read_text(encoding="utf-8"))
    rows = [
        r
        for r in payload["results"]
        if r.get("generated") and r.get("label") in ({"correct"} | FAILURE_LABELS)
    ]
    if not rows:
        raise SystemExit("No labelled, generated rows found. Run run_eval.py then label.py.")
    return rows


def composite_for(row: dict, w: tuple[float, float, float]) -> float:
    total = w[0] * row["s1"] + w[1] * row["s2"] + w[2] * row["s3"]
    return total / sum(w)


def auc(scores: np.ndarray, good: np.ndarray) -> float:
    """Probability that a randomly chosen correct answer outscores a failure.

    Computed by rank statistic so ties count as half, which matters here: the
    sample is small and grounding scores collide on round values.
    """
    pos, neg = scores[good], scores[~good]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(scores)
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1)
    # average ranks over ties
    for value in np.unique(scores):
        mask = scores == value
        if mask.sum() > 1:
            ranks[mask] = ranks[mask].mean()
    rank_sum = ranks[good].sum()
    n_pos, n_neg = len(pos), len(neg)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def fit_weights(rows: list[dict]) -> tuple[tuple[float, float, float], float]:
    """Grid search on the simplex, keeping w2 strictly the largest weight."""
    good = np.array([r["label"] == "correct" for r in rows])
    best, best_auc = None, -1.0
    grid = [round(x, 2) for x in np.arange(0.05, 0.91, 0.05)]

    for w1, w3 in product(grid, repeat=2):
        w2 = round(1.0 - w1 - w3, 2)
        if w2 <= 0 or w2 <= max(w1, w3):  # report 4.3: S2 carries the largest weight
            continue
        scores = np.array([composite_for(r, (w1, w2, w3)) for r in rows])
        value = auc(scores, good)
        if not np.isnan(value) and value > best_auc:
            best, best_auc = (w1, w2, w3), value

    if best is None:
        raise SystemExit("Weight fitting found no admissible combination.")
    return best, best_auc


def sweep(rows: list[dict], w: tuple[float, float, float]) -> list[dict]:
    """Precision on auto-answered queries and escalation rate per threshold."""
    points = []
    for threshold in np.arange(0.0, 1.001, 0.01):
        auto = [
            r
            for r in rows
            if composite_for(r, w) >= threshold and r.get("coverage_passed") is not False
        ]
        correct = sum(1 for r in auto if r["label"] == "correct")
        points.append(
            {
                "threshold": round(float(threshold), 3),
                "auto_answered": len(auto),
                "auto_correct": correct,
                "precision": (correct / len(auto)) if auto else None,
                "escalation_rate": 1 - len(auto) / len(rows),
            }
        )
    return points


def pick_threshold(points: list[dict], target: float, min_auto: int) -> dict | None:
    """Lowest threshold meeting the precision target.

    min_auto guards against the degenerate optimum: a threshold so high that one
    query survives, it happens to be correct, and precision reads 100%.
    """
    for point in points:
        if (
            point["precision"] is not None
            and point["precision"] >= target
            and point["auto_answered"] >= min_auto
        ):
            return point
    return None


def plot_distribution(rows, w, threshold, path: Path) -> None:
    good = [composite_for(r, w) for r in rows if r["label"] == "correct"]
    bad = [composite_for(r, w) for r in rows if r["label"] in FAILURE_LABELS]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = np.linspace(0, 1, 21)
    ax.hist(good, bins=bins, alpha=0.65, label=f"korrekt (n={len(good)})", color="#2a7f5f")
    ax.hist(bad, bins=bins, alpha=0.65, label=f"falsch/unvollständig (n={len(bad)})", color="#b3452c")
    if threshold is not None:
        ax.axvline(threshold, color="#1c1c1c", linestyle="--", linewidth=1.6,
                   label=f"Schwellenwert {threshold:.2f}")
    ax.set_xlabel("Composite confidence C")
    ax.set_ylabel("Anzahl Testfragen")
    ax.set_title("Verteilung des Vertrauenswerts nach Bewertung (PM4)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_sweep(points, threshold, target, path: Path) -> None:
    xs = [p["threshold"] for p in points]
    prec = [p["precision"] if p["precision"] is not None else np.nan for p in points]
    esc = [p["escalation_rate"] for p in points]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(xs, prec, color="#2a7f5f", label="Precision auf automatisch beantworteten Fragen")
    ax.plot(xs, esc, color="#b3452c", label="Eskalationsrate")
    ax.axhline(target, color="#888", linestyle=":", linewidth=1.2, label=f"Sicherheitsziel {target:.0%}")
    if threshold is not None:
        ax.axvline(threshold, color="#1c1c1c", linestyle="--", linewidth=1.6,
                   label=f"gewählter Schwellenwert {threshold:.2f}")
    ax.set_xlabel("Schwellenwert")
    ax.set_ylabel("Anteil")
    ax.set_ylim(0, 1.05)
    ax.set_title("Precision und Eskalationsrate in Abhängigkeit vom Schwellenwert (PM4)")
    ax.legend(loc="lower left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    target = cfg["confidence"]["target_precision_on_auto_answered"]

    rows = load_rows()
    weights, fitted_auc = fit_weights(rows)
    points = sweep(rows, weights)
    min_auto = max(3, len(rows) // 10)
    chosen = pick_threshold(points, target, min_auto)

    threshold = chosen["threshold"] if chosen else None
    plot_distribution(rows, weights, threshold, FIG_DIR / "fig_score_distribution.png")
    plot_sweep(points, threshold, target, FIG_DIR / "fig_threshold_sweep.png")

    payload = {
        "n_labelled": len(rows),
        "n_correct": sum(1 for r in rows if r["label"] == "correct"),
        "n_failure": sum(1 for r in rows if r["label"] in FAILURE_LABELS),
        "fitted_weights": {
            "s1_retrieval_strength": weights[0],
            "s2_grounding": weights[1],
            "s3_self_assessment": weights[2],
        },
        "fitted_auc": round(float(fitted_auc), 4),
        "target_precision": target,
        "min_auto_answered_required": min_auto,
        "calibrated_threshold": threshold,
        "at_threshold": chosen,
        "placeholder_threshold": cfg["confidence"]["threshold_placeholder"],
        "sweep": points,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Labelled rows used:      {len(rows)}  "
          f"({payload['n_correct']} korrekt / {payload['n_failure']} falsch-unvollständig)")
    print(f"Fitted weights:          S1={weights[0]:.2f}  S2={weights[1]:.2f}  S3={weights[2]:.2f}")
    print(f"Separation (AUC):        {fitted_auc:.3f}")
    if chosen:
        print(f"Calibrated threshold:    {threshold:.3f}   "
              f"(placeholder was {payload['placeholder_threshold']})")
        print(f"  precision auto-answered {chosen['precision']:.1%} on {chosen['auto_answered']} queries")
        print(f"  escalation rate         {chosen['escalation_rate']:.1%}  <- operational cost")
    else:
        print(f"NO threshold reaches the {target:.0%} precision target while auto-answering "
              f"at least {min_auto} queries.")
        print("  That is itself the finding: on this corpus the safety target is not met at any "
              "threshold, and the gate must record it rather than lowering the target.")
    print(f"\nFigures -> {FIG_DIR / 'fig_score_distribution.png'}")
    print(f"           {FIG_DIR / 'fig_threshold_sweep.png'}")

    if "--apply" in sys.argv and threshold is not None:
        text = (ROOT / "config.yaml").read_text(encoding="utf-8")
        text = text.replace("  calibrated_threshold: null", f"  calibrated_threshold: {threshold}")
        (ROOT / "config.yaml").write_text(text, encoding="utf-8", newline="\n")
        print(f"\nconfig.yaml updated: calibrated_threshold = {threshold}")


if __name__ == "__main__":
    main()
