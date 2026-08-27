"""
Step 5b - Labelling.

Report 5.6 requires every output to be reviewed by a Traffic Department
caseworker against the source documents, and labelled correct / incorrect /
incomplete. That human review is the evidence base for the whole PM4 result.

This script does NOT replace it. It produces a machine PRE-LABEL against the
gold facts in the test set, plus a review sheet (CSV) with the pre-label, the
answer and the sources, so the caseworker confirms or overrides each row rather
than starting from a blank page. Any figure produced before that sheet comes
back is provisional and must be reported as such.

  correct     - all gold facts present and nothing stated that the sources
                do not support
  incomplete  - everything stated is correct, but a gold fact is missing.
                This is the PoC's own failure mode (report 5.6) and is tracked
                separately from incorrect for exactly that reason.
  incorrect   - states something the sources do not support, or contradicts them
  n_a         - correctly escalated or hard-routed; no answer to label

    python eval/label.py                 # pre-label, write review sheet
    python eval/label.py --merge         # merge caseworker review back in
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from llm import structured  # noqa: E402

RAW = ROOT / "eval" / "results" / "raw_results.json"
SHEET = ROOT / "eval" / "results" / "review_sheet.csv"
LABELS = ROOT / "eval" / "results" / "labels.json"

VALID = {"correct", "incomplete", "incorrect", "n_a"}

SYSTEM = """Du bewertest die Antwort eines behördlichen Auskunftssystems der Gemeinde Schwyz.

Du erhältst die Frage, die erwarteten Sollfakten aus den Quelldokumenten und die
tatsächliche Antwort. Vergib genau eine Bewertung:

- "correct": Alle Sollfakten sind sinngemäss enthalten und es wird nichts
  behauptet, was den Quellen widerspricht.
- "incomplete": Alles Gesagte ist richtig, aber mindestens ein Sollfakt fehlt.
  Insbesondere: eine Gebühr, ein Betrag oder eine Frist wurde nicht genannt,
  obwohl sie zu den Sollfakten gehört.
- "incorrect": Es wird etwas behauptet, was falsch ist oder den Quellen
  widerspricht.

Massstab: Zahlen, Beträge, Fristen und Zeiten müssen sachlich übereinstimmen.
Abweichende Formulierung ist kein Fehler. Eine ausdrückliche Aussage, dass die
Quellen die Frage nicht beantworten, ist "correct", wenn das zutrifft."""

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["correct", "incomplete", "incorrect"]},
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
        "justification": {"type": "string"},
    },
    "required": ["label", "missing_facts", "unsupported_claims", "justification"],
}


def prelabel(record: dict) -> dict:
    """Pre-label one record.

    Report 4.3 calibrates on the answer EVERY test query produced, then derives
    the threshold from that labelled distribution. So the draft answer is
    labelled even when routing escalated it - otherwise the escalated cases,
    which are exactly the ones the threshold has to separate, would be missing
    from the very data used to set the threshold.

    Only hard-routed queries are unlabelled, because nothing was generated for
    them at all (report 4.4).
    """
    if not record.get("generated"):
        return {
            "label": "n_a",
            "missing_facts": [],
            "unsupported_claims": [],
            "justification": "Hart geroutet - kein Antwortversuch (Bericht 4.4).",
        }

    answer = record.get("draft_answer") or record.get("answer") or ""
    gold = record.get("gold_facts") or []
    if not gold:
        # Out-of-scope and ambiguous cases carry no gold facts: the correct
        # behaviour is to state that the sources do not answer the question.
        user = (
            f"Frage:\n{record['query']}\n\n"
            "Sollfakten: keine. Zu dieser Frage enthält der Korpus keine Antwort. "
            "Korrekt ist daher ausschliesslich eine Antwort, die das ausdrücklich "
            "sagt und keine Sachbehauptung aufstellt.\n\n"
            f"Tatsächliche Antwort:\n{answer}"
        )
    else:
        user = (
            f"Frage:\n{record['query']}\n\n"
            + "Sollfakten aus den Quelldokumenten:\n"
            + "\n".join(f"- {g}" for g in gold)
            + f"\n\nTatsächliche Antwort:\n{answer}"
        )
    return structured(
        system=SYSTEM,
        user=user,
        tool_name="bewertung",
        schema=SCHEMA,
        max_tokens=900,
        temperature=0.0,
    )


def write_sheet(records: list[dict]) -> None:
    with open(SHEET, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            [
                "id",
                "kategorie",
                "frage",
                "entscheid",
                "antwort",
                "sollfakten",
                "vorlabel",
                "begruendung_vorlabel",
                "LABEL_SACHBEARBEITUNG",
                "BEMERKUNG_SACHBEARBEITUNG",
            ]
        )
        for r in records:
            writer.writerow(
                [
                    r["id"],
                    r["category"],
                    r["query"],
                    r["decision"],
                    r.get("draft_answer") or r["answer"],
                    " | ".join(r.get("gold_facts") or []),
                    r["prelabel"]["label"],
                    r["prelabel"]["justification"],
                    "",  # caseworker fills this
                    "",
                ]
            )


def merge_review() -> None:
    """Read the caseworker column back and let it override every pre-label."""
    if not SHEET.exists():
        raise SystemExit(f"No review sheet at {SHEET}")
    payload = json.loads(LABELS.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in payload["results"]}

    confirmed = overridden = 0
    with open(SHEET, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            human = (row.get("LABEL_SACHBEARBEITUNG") or "").strip().lower()
            if not human:
                continue
            if human not in VALID:
                print(f"  {row['id']}: ignoring invalid label {human!r}")
                continue
            record = by_id.get(row["id"])
            if record is None:
                continue
            if human != record["prelabel"]["label"]:
                overridden += 1
            else:
                confirmed += 1
            record["label"] = human
            record["label_source"] = "caseworker"
            record["label_note"] = (row.get("BEMERKUNG_SACHBEARBEITUNG") or "").strip()

    reviewed = confirmed + overridden
    payload["review"] = {
        "reviewed": reviewed,
        "confirmed": confirmed,
        "overridden": overridden,
        "complete": reviewed == len(payload["results"]),
    }
    LABELS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Merged {reviewed} caseworker labels "
        f"({confirmed} confirmed, {overridden} overridden) of {len(payload['results'])}."
    )
    if reviewed < len(payload["results"]):
        print("Review INCOMPLETE - results remain provisional.")


def main() -> None:
    if "--merge" in sys.argv:
        merge_review()
        return

    payload = json.loads(RAW.read_text(encoding="utf-8"))
    records = [r for r in payload["results"] if "error" not in r]

    for i, record in enumerate(records, 1):
        record["prelabel"] = prelabel(record)
        record["label"] = record["prelabel"]["label"]
        record["label_source"] = "prelabel"
        print(f"[{i:>3}/{len(records)}] {record['id']}  {record['label']}")

    LABELS.write_text(
        json.dumps(
            {"source_run": payload["run_at"], "review": None, "results": records},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_sheet(records)
    print(f"\nPre-labels -> {LABELS}")
    print(f"Review sheet for the Traffic Department -> {SHEET}")
    print("Fill column LABEL_SACHBEARBEITUNG, then run: python eval/label.py --merge")


if __name__ == "__main__":
    main()
