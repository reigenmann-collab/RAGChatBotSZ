"""
Report 4.3 - Composite confidence scoring.

The escalation mechanism depends entirely on this score, so how it is computed
determines whether the safety architecture works at all. A RAG pipeline does not
produce a calibrated confidence value by itself:

  - Retrieval similarity measures whether related text was found, not whether
    the generated answer is correct.
  - A model's self-reported certainty is poorly calibrated, particularly when it
    is confidently wrong (Guo et al. 2017; Kadavath et al. 2022).

Treating either alone as a confidence score would produce a safety mechanism
that fails precisely in the cases it exists to catch. Hence a weighted composite
of three independent signals:

  S1  Retrieval strength    - mean cosine similarity of the top-k chunks.
  S2  Answer-source grounding - entailment of each factual claim in the answer
                                against the retrieved chunks (Es et al. 2024).
                                Carries the largest weight: grounding failure is
                                the failure mode with the most serious
                                consequence for a public authority.
  S3  Model self-assessment - a third weak signal, never decisive on its own.

  C = w1*S1 + w2*S2 + w3*S3

Note that completeness is NOT part of C. An answer can be fully grounded and
still omit material information from a document that was never retrieved; that
is handled separately by the REQ-11 coverage check, because completeness and
correctness are different properties.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402
from generate import format_context  # noqa: E402
from llm import structured  # noqa: E402

CFG = load_config()
WEIGHTS = CFG["confidence"]["weights"]

GROUNDING_SYSTEM = """Du bist ein strenger Faktenprüfer für ein behördliches Auskunftssystem.

Du zerlegst eine Antwort in einzelne, überprüfbare Sachaussagen und prüfst jede
ausschliesslich gegen die bereitgestellten Quellenauszüge.

Bewertung je Aussage:
- "gedeckt": Die Aussage folgt direkt und eindeutig aus den Auszügen.
- "teilweise": Die Auszüge stützen die Aussage nur teilweise oder ungenau.
- "nicht_gedeckt": Die Auszüge stützen die Aussage nicht, oder sie widersprechen ihr.

Sei streng. Plausibilität ist keine Deckung. Allgemeinwissen ist keine Deckung.
Reine Verfahrenshinweise ohne Sachbehauptung (z. B. "wenden Sie sich an die
Gemeinde") zählen nicht als Sachaussage und lässt du weg."""

GROUNDING_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "Die Sachaussage."},
                    "verdict": {
                        "type": "string",
                        "enum": ["gedeckt", "teilweise", "nicht_gedeckt"],
                    },
                    "evidence_chunk_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["claim", "verdict", "evidence_chunk_ids"],
            },
        }
    },
    "required": ["claims"],
}

VERDICT_VALUE = {"gedeckt": 1.0, "teilweise": 0.5, "nicht_gedeckt": 0.0}


def s1_retrieval_strength(hits: list[dict]) -> float:
    """Mean cosine similarity of the top-k chunks, clamped to [0, 1].

    A low value means the question falls outside the indexed domain.
    """
    if not hits:
        return 0.0
    mean = sum(h["similarity"] for h in hits) / len(hits)
    return max(0.0, min(1.0, mean))


def s2_grounding(query: str, answer: str, hits: list[dict]) -> tuple[float, list[dict]]:
    """Fraction of the answer's factual claims that the retrieved chunks support.

    An answer that makes no checkable factual claim scores 0.0 rather than 1.0:
    a refusal must not be able to reach the auto-answer threshold on a vacuous
    perfect grounding score.
    """
    if not hits or not answer.strip():
        return 0.0, []

    user = (
        f"Frage:\n{query}\n\n"
        f"Zu prüfende Antwort:\n{answer}\n\n"
        f"Quellenauszüge:\n{format_context(hits)}"
    )
    try:
        result = structured(
            system=GROUNDING_SYSTEM,
            user=user,
            tool_name="deckungspruefung",
            schema=GROUNDING_SCHEMA,
            max_tokens=2000,
            temperature=0.0,
        )
    except Exception:  # noqa: BLE001 - an unverifiable answer is an unsafe answer
        return 0.0, []

    claims = result.get("claims", [])
    if not claims:
        return 0.0, []

    total = sum(VERDICT_VALUE.get(c.get("verdict", "nicht_gedeckt"), 0.0) for c in claims)
    return total / len(claims), claims


def composite(s1: float, s2: float, s3: float, weights: dict | None = None) -> float:
    w = weights or WEIGHTS
    total = (
        w["s1_retrieval_strength"] * s1
        + w["s2_grounding"] * s2
        + w["s3_self_assessment"] * s3
    )
    denom = sum(w.values())
    return total / denom if denom else 0.0


def score(query: str, answer: str, hits: list[dict], self_assessment: float) -> dict:
    s1 = s1_retrieval_strength(hits)
    s2, claims = s2_grounding(query, answer, hits)
    s3 = max(0.0, min(1.0, float(self_assessment)))
    return {
        "s1_retrieval_strength": round(s1, 4),
        "s2_grounding": round(s2, 4),
        "s3_self_assessment": round(s3, 4),
        "composite": round(composite(s1, s2, s3), 4),
        "weights": dict(WEIGHTS),
        "claims": claims,
    }
