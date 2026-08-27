"""
Report 4.4 - Escalation and routing logic.

Two INDEPENDENT mechanisms, kept separate on purpose:

  1. Topic-based hard routing. Legal disputes, appeals and objections go to a
     human with no automated answer attempt, irrespective of confidence. These
     are cases where the system may well know the answer but should not be the
     one giving it.
  2. Confidence-based escalation, plus the REQ-11 coverage check. These are
     cases where the system does not know the answer well enough.

Collapsing them into one score would mean a confidently answered legal question
gets delivered automatically - the outcome a public authority must avoid.
"""
from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402

CFG = load_config()
ROUTE = CFG["routing"]


class Decision(str, Enum):
    ANSWER = "answer"
    ESCALATE_CONFIDENCE = "escalate_confidence"
    ESCALATE_COVERAGE = "escalate_coverage"
    HARD_ROUTE = "hard_route"


def is_hard_routed(query: str) -> tuple[bool, list[str]]:
    q = query.lower()
    matched = [p for p in ROUTE["hard_route_patterns"] if p in q]
    return bool(matched), matched


def active_threshold() -> float:
    """The calibrated threshold once calibration has run, otherwise the planning
    placeholder. The report is explicit that these are not the same thing."""
    conf = CFG["confidence"]
    return conf.get("calibrated_threshold") or conf["threshold_placeholder"]


def decide(query: str, composite: float | None, coverage: dict | None) -> dict:
    """Evaluate hard routing first, then coverage, then confidence."""
    hard, matched = is_hard_routed(query)
    if hard:
        return {
            "decision": Decision.HARD_ROUTE,
            "escalate": True,
            "reason": ROUTE["hard_route_reason"],
            "matched_terms": matched,
            "threshold": active_threshold(),
        }

    threshold = active_threshold()

    if coverage is not None and not coverage["passed"]:
        return {
            "decision": Decision.ESCALATE_COVERAGE,
            "escalate": True,
            "reason": coverage["reason"],
            "matched_terms": [],
            "threshold": threshold,
        }

    if composite is None or composite < threshold:
        shown = "n/a" if composite is None else f"{composite:.3f}"
        return {
            "decision": Decision.ESCALATE_CONFIDENCE,
            "escalate": True,
            "reason": (
                f"Vertrauenswert {shown} liegt unter dem kalibrierten "
                f"Schwellenwert {threshold:.3f}."
            ),
            "matched_terms": [],
            "threshold": threshold,
        }

    return {
        "decision": Decision.ANSWER,
        "escalate": False,
        "reason": f"Vertrauenswert {composite:.3f} erreicht den Schwellenwert {threshold:.3f}.",
        "matched_terms": [],
        "threshold": threshold,
    }
