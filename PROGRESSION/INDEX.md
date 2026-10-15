# PROGRESSION — session log index

Running history of what happened to this prototype, newest first. Each entry is
one working session: what changed, what was decided, what broke, and what was
left open.

This exists so a session starting cold does not have to re-derive the project
state from the code, and does not accidentally undo a decision that was
expensive to arrive at.

| # | Date(s) | Summary | Left open |
|---|---|---|---|
| [001](001-prototype-build-and-deploy.md) | 2026-08-26 → 2026-09-04 | Built the PM4 prototype from the written report's spec; corpus reconnaissance turned up five findings that contradict the report; migrated Anthropic → Gemini; deployed to Streamlit Cloud; restyled the demo to match gemeindeschwyz.ch; set up the CLAUDE.md + `pm4-project-context` skill handoff (see 001 §9); short recap in [`docs/SESSION_RECAP_fromCode_PM4 prototype status.md`](<../docs/SESSION_RECAP_fromCode_PM4 prototype status.md>) | Evaluation chain never run end to end — threshold still the 0.82 placeholder, no PAA figures, caseworker review sheet not produced |
| [002](002-report-v4_1-audit.md) | 2026-10-15 | Explained REQ-11 coverage-check implementation; built a backup slide (B17) for it; discovered the governing report had moved/renamed (v2→v4.1, EN→DE, new folder) and fixed three stale references across `CLAUDE.md`/`decisions.md`/`FOLDER-DESCRIPTION.md`; confirmed session 001's 150-query-gate finding was adopted into the report's roadmap | OCR-budgeting gap (001 finding 4) still not in the report; B17 slide not yet merged into the deck; eval chain still not run |
| [003](003-pm3-rebrand-and-topic-match-switch.md) | 2026-10-15 | Rebranded app UI from "PM4 — Departementaler Pilot" to "PM3 — PoC-Demonstrator" everywhere; switched the legal/sensitive hard-routing mechanism from a 24-keyword list to embedding similarity against a curated reference set (report v4.3 §4.2/§4.3), reusing the retrieval query vector at no extra model call; old keyword list archived to `docs/PM4_Stichwortlisten_Themenabgleich_REQ11.xlsx`; new `legal_sensitive_similarity_threshold: 0.65` is empirically sanity-checked, not calibrated; committed and pushed (`2a1fe7e`) | New similarity threshold needs a negative-control test before go-live; reference set (18 examples) well short of the report's recommended 50–150 |
| [004](004-deploy-verification-fastembed-pin.md) | 2026-10-15 | Post-deploy verification of 003 found a borderline topic-match query (similarity 0.718 locally) didn't trigger on Streamlit Cloud, falling through to confidence-based escalation instead — same citizen outcome, wrong mechanism. Traced to unpinned `fastembed`, letting Cloud resolve a different version than local dev. Pinned `fastembed==0.8.0` + `onnxruntime==1.29.0` | Fix pushed but **not yet re-verified** against the live deployment; pinning may narrow but not fully close cross-platform ONNX numeric drift on the quantised model |

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
