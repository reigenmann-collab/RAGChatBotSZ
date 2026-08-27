"""
REQ-11 - Coverage check.

Report 4.3: an answer can be correct as far as it goes yet omit material
information held in a document that was never retrieved. The model is
legitimately confident, because what it did retrieve does support what it said.
No confidence signal detects this, so completeness is checked separately and
treated as a routing trigger in its own right.

The rule is deliberately blunt: if a query is about a topic whose authoritative
answer requires a document type, and no chunk of that type was retrieved, the
answer is flagged - regardless of how good it looks.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402

CFG = load_config()
COV = CFG["coverage"]


def classify_topics(query: str) -> list[dict]:
    """Return every coverage rule whose patterns appear in the query."""
    q = query.lower()
    return [rule for rule in COV["rules"] if any(p in q for p in rule["query_patterns"])]


def check(query: str, hits: list[dict]) -> dict:
    """Evaluate coverage for one query against the retrieved chunks."""
    if not COV.get("enabled", True):
        return {"passed": True, "topics": [], "missing": [], "reason": "coverage check disabled"}

    topics = classify_topics(query)
    retrieved_types = {h["doc_type"] for h in hits}

    missing: list[dict] = []
    for rule in topics:
        required = set(rule["required_doc_types"])
        if not (required & retrieved_types):
            missing.append(
                {
                    "topic": rule["topic"],
                    "description": rule["description"],
                    "required_doc_types": sorted(required),
                }
            )

    if missing:
        detail = "; ".join(
            f"{m['topic']} erwartet {'/'.join(m['required_doc_types'])}" for m in missing
        )
        reason = (
            "Deckungsprüfung nicht bestanden: zur Frage wurde kein Dokument des "
            f"erwarteten Typs gefunden ({detail}). Die Antwort könnte richtig, aber "
            "unvollständig sein."
        )
    else:
        reason = "Deckungsprüfung bestanden."

    return {
        "passed": not missing,
        "topics": [r["topic"] for r in topics],
        "missing": missing,
        "retrieved_doc_types": sorted(retrieved_types),
        "reason": reason,
    }
