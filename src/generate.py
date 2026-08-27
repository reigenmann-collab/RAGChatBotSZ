"""
Step 4 - Answer generation (report 4.1).

The model answers strictly from the retrieved municipal document chunks. It is
instructed to refuse rather than improvise, because for a public authority a
fluent wrong answer is worse than no answer (report 1.2).

The call also returns the model's own certainty. That value becomes S3 in the
composite score - used only as a weak third signal, never decisive on its own,
because model self-assessment is known to be poorly calibrated exactly when the
model is confidently wrong (Guo et al. 2017; Kadavath et al. 2022).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402
from llm import structured  # noqa: E402

CFG = load_config()
GEN = CFG["generation"]

SYSTEM = """Du bist der Auskunfts-Assistent der Gemeinde Schwyz für Fragen zu Strassenverkehr und Parkieren.

Grundregeln:
1. Du antwortest AUSSCHLIESSLICH auf Grundlage der bereitgestellten Quellenauszüge. Du verwendest kein eigenes Vorwissen.
2. Wenn die Quellen die Frage nicht oder nur teilweise beantworten, sagst du das ausdrücklich. Erfinde nichts und schliesse nichts aus Plausibilität.
3. Du antwortest auf Deutsch, sachlich, knapp und in ganzen Sätzen (höchstens rund 120 Wörter).
4. Jede Sachaussage muss durch die Quellenauszüge gedeckt sein. Gib die verwendeten Quellen-IDs an.
5. Du bist eine Auskunft, keine Verfügung. Du triffst keine Rechtsentscheide und gibst keine Rechtsberatung.
6. Beträge, Fristen, Zeiten und Paragraphen gibst du exakt so wieder, wie sie in den Quellen stehen."""

USER_TEMPLATE = """Frage der Bürgerin oder des Bürgers:
{query}

Quellenauszüge aus den Dokumenten der Gemeinde Schwyz:
{context}

Beantworte die Frage ausschliesslich aus diesen Auszügen."""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "Die Antwort auf Deutsch, ausschliesslich aus den Quellen abgeleitet.",
        },
        "cited_chunk_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Die chunk_id jedes tatsächlich verwendeten Auszugs.",
        },
        "answerable_from_sources": {
            "type": "boolean",
            "description": "True, wenn die Quellen die Frage vollständig beantworten.",
        },
        "self_assessment": {
            "type": "number",
            "description": "Eigene Sicherheit von 0.0 bis 1.0, dass die Antwort korrekt und vollständig ist.",
        },
    },
    "required": [
        "answer",
        "cited_chunk_ids",
        "answerable_from_sources",
        "self_assessment",
    ],
}


def format_context(hits: list[dict]) -> str:
    blocks = []
    for hit in hits:
        blocks.append(
            f"[{hit['chunk_id']}] Dokument: {hit['doc_title']} "
            f"(Typ: {hit['doc_type']}, Quelle: {hit['source_url']})\n{hit['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def generate_answer(query: str, hits: list[dict]) -> dict:
    if not hits:
        return {
            "answer": "Zu dieser Frage liegen mir keine Dokumente der Gemeinde Schwyz vor.",
            "cited_chunk_ids": [],
            "answerable_from_sources": False,
            "self_assessment": 0.0,
        }

    result = structured(
        system=SYSTEM,
        user=USER_TEMPLATE.format(query=query, context=format_context(hits)),
        tool_name="antwort",
        schema=SCHEMA,
        max_tokens=GEN["max_tokens"],
        temperature=GEN["temperature"],
    )
    result["self_assessment"] = max(0.0, min(1.0, float(result.get("self_assessment", 0.0))))
    return result


# --- Escalation summary (REQ-03) --------------------------------------------

SUMMARY_SYSTEM = """Du bereitest Eskalationen für Sachbearbeitende der Gemeinde Schwyz auf.

Der Sachbearbeitende soll einen vorbereiteten Fall erhalten, nicht ein Rohprotokoll.
Fasse dich kurz, sachlich und auf Deutsch. Erfinde keine Sachverhalte."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "betreff": {"type": "string", "description": "Kurzer Betreff, höchstens 80 Zeichen."},
        "anliegen": {"type": "string", "description": "Das Anliegen in ein bis zwei Sätzen."},
        "eskalationsgrund": {
            "type": "string",
            "description": "Warum dieser Fall an einen Menschen geht.",
        },
        "gefundene_grundlagen": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Titel der gefundenen einschlägigen Dokumente, falls vorhanden.",
        },
        "offene_punkte": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Was der Sachbearbeitende konkret klären muss.",
        },
    },
    "required": [
        "betreff",
        "anliegen",
        "eskalationsgrund",
        "gefundene_grundlagen",
        "offene_punkte",
    ],
}


def generate_summary(query: str, hits: list[dict], routing: dict) -> dict:
    """Report 4.4: every escalation carries an auto-generated summary.

    Business continuity (report 7.4): if this fails the raw inquiry must still
    reach the case queue, so a failure degrades the summary and never drops the
    request.
    """
    sources = "\n".join(f"- {h['doc_title']} ({h['doc_type']})" for h in hits) or "- keine"
    user = (
        f"Anfrage:\n{query}\n\n"
        f"Eskalationsgrund (technisch):\n{routing['reason']}\n\n"
        f"Im Korpus gefundene Dokumente:\n{sources}"
    )
    try:
        return structured(
            system=SUMMARY_SYSTEM,
            user=user,
            tool_name="eskalation",
            schema=SUMMARY_SCHEMA,
            max_tokens=GEN["summary_max_tokens"],
            temperature=GEN["temperature"],
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "betreff": "Bürgeranfrage Strassenverkehr (Zusammenfassung fehlgeschlagen)",
            "anliegen": query,
            "eskalationsgrund": routing["reason"],
            "gefundene_grundlagen": [h["doc_title"] for h in hits],
            "offene_punkte": [
                "Zusammenfassung technisch fehlgeschlagen - Rohanfrage prüfen."
            ],
            "summary_error": repr(exc),
        }
