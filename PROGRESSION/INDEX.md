# PROGRESSION — session log index

Running history of what happened to this prototype, newest first. Each entry is
one working session: what changed, what was decided, what broke, and what was
left open.

This exists so a session starting cold does not have to re-derive the project
state from the code, and does not accidentally undo a decision that was
expensive to arrive at.

| # | Date(s) | Summary | Left open |
|---|---|---|---|
| [001](001-prototype-build-and-deploy.md) | 2026-08-26 → 2026-09-04 | Built the PM4 prototype from the written report's spec; corpus reconnaissance turned up five findings that contradict the report; migrated Anthropic → Gemini; deployed to Streamlit Cloud; restyled the demo to match gemeindeschwyz.ch | Evaluation chain never run end to end — threshold still the 0.82 placeholder, no PAA figures, caseworker review sheet not produced |

---

## Current state, in one paragraph

The prototype works end to end and is deployed. The corpus (7 documents, 36
chunks) covers municipal road traffic and parking for Gemeinde Schwyz. The
outstanding work is **evidence, not code**: `eval/run_eval.py → label.py →
calibrate.py --apply → report_results.py` has never been run, so the operating
threshold is still the planning placeholder rather than a derived value, and
there are no PM4 result figures yet.

---

## How to add an entry

At the end of a session that changed something, add
`NNN-short-slug.md` here and a row in the table above. Keep entries factual and
specific — dates, decisions and their reasons, bugs and their root causes, and
an honest statement of what was left unfinished. A future session trusts this
file; vagueness costs it real time.

If the folder layout changed, also refresh the folder map:

```bash
python .claude/skills/pm4-project-context/scripts/refresh_folder_description.py
```
