"""
Report v4.3 4.3 - Escalation and routing logic.

THREE independent triggers, kept separate on purpose:

  1. Topic-based hard routing. Legal disputes, appeals and sensitive queries go
     to a human with no automated answer attempt, irrespective of confidence.
     These are cases where the system may well know the answer but should not
     be the one giving it. Detected by embedding similarity against a curated
     reference set (topic_match.py), not keyword matching - see that module's
     docstring for why.
  2. Coverage check failure (REQ-11).
  3. Composite confidence below the calibrated threshold.

Triggers 2 and 3 both mean "the system does not know the answer well enough"
and are evaluated after generation; trigger 1 means "the system should not be
the one answering" and is evaluated BEFORE generation is even attempted.
Collapsing them into one score would mean a confidently answered legal question
gets delivered automatically - the outcome a public authority must avoid.
"""
from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402
from topic_match import is_topic_match  # noqa: E402

CFG = load_config()
ROUTE = CFG["routing"]


class Decision(str, Enum):
    ANSWER = "answer"
    ESCALATE_CONFIDENCE = "escalate_confidence"
    ESCALATE_COVERAGE = "escalate_coverage"
    HARD_ROUTE = "hard_route"


def is_hard_routed(query_vec: np.ndarray) -> dict:
    """query_vec: the precomputed embedding from retrieve.embed_query(query) -
    reused here so the topic match costs no extra model call (report 4.1)."""
    return is_topic_match(query_vec)


def active_threshold() -> float:
    """The calibrated threshold once calibration has run, otherwise the planning
    placeholder. The report is explicit that these are not the same thing."""
    conf = CFG["confidence"]
    return conf.get("calibrated_threshold") or conf["threshold_placeholder"]


def decide(
    query_vec: np.ndarray, composite: float | None, coverage: dict | None
) -> dict:
    """Evaluate hard routing first, then coverage, then confidence."""
    topic = is_hard_routed(query_vec)
    if topic["matched"]:
        return {
            "decision": Decision.HARD_ROUTE,
            "escalate": True,
            "reason": ROUTE["hard_route_reason"],
            "matched_terms": [topic["nearest_example"]],
            "topic_match": topic,
            "threshold": active_threshold(),
        }

    threshold = active_threshold()

    if coverage is not None and not coverage["passed"]:
        return {
            "decision": Decision.ESCALATE_COVERAGE,
            "escalate": True,
            "reason": coverage["reason"],
            "matched_terms": [],
            "topic_match": topic,
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
            "topic_match": topic,
            "threshold": threshold,
        }

    return {
        "decision": Decision.ANSWER,
        "escalate": False,
        "reason": f"Vertrauenswert {composite:.3f} erreicht den Schwellenwert {threshold:.3f}.",
        "matched_terms": [],
        "topic_match": topic,
        "threshold": threshold,
    }
