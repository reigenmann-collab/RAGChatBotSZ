# 002 — Report v4.1 audit: coverage check explainer, stale-reference sweep

**Date:** 2026-10-15
**Outcome:** No code changes. Fixed three stale references in the session-handoff
docs; produced a standalone backup slide explaining REQ-11's implementation.

---

## 1. Trigger

User asked how the coverage check (REQ-11) is actually implemented — the report
explains *why* it exists but not *how* — and wanted a backup slide for it. That
required reading the current governing report, which turned out not to be the
file any of the handoff docs pointed to.

## 2. The report moved, renamed, and changed content since session 001

Session 001 cited `../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`.
That file no longer exists at that path — it was archived to
`RAG Project/history/`. The current, governing version is:

```
RAG Project/_RAG_withPilot/REI_Community-RAG-Chatbot_AIBS_Projektbericht_v4_1_DE.docx
```

English → German, v2 → v4.1, and a new subfolder. The outer `RAG Project/`
folder has ~30 loose files including several intermediate report versions
(v3.9, v4.0 docx+pdf) — the `_RAG_withPilot/` subfolder is the one with the
current report plus the current executive deck and architecture figures.

**Caught mid-session:** the first read of the report came back with text that
didn't match what the user quoted from their open Word window. Diagnosis: the
`.docx` on disk still had Word's unsaved edits pending (visible via the `~$I_...`
lock file and a `~WRL*.tmp` autosave); `document.xml` still carried `<w:ins>`/
`<w:del>` tracked-change markup for the very paragraphs in question. Asked the
user to save in Word, then re-read — clean, no tracked-change markup, content
matched. **Lesson:** if an extracted `.docx` paragraph doesn't match what the
user is looking at, check for a `~$`-prefixed lock file before trusting the
extraction; a currently-open Word doc can be ahead of its own last save.

## 3. What changed in the report, content-wise, since session 001 read it

- **§4.2 vs §4.3 split clarified.** §4.2 now carries the "fourth signal —
  coverage" rationale (why no confidence signal catches it). §4.3 now opens
  with "Drei Auslöser ... zwei verschiedene Fragen" — explicitly three
  independent escalation triggers (confidence threshold, coverage check, hard
  routing), not two. `decisions.md` cited this reasoning to §4.3; corrected to
  §4.2 (restated in §4.3).
- **The 150-query gate finding was adopted.** Session 001's corpus
  reconnaissance (finding 5) flagged that expanding the test set to 150 queries
  wasn't in the report's roadmap. Report v4.1 §7.2 (Phase 1 / Gate 1) now
  makes exactly that an explicit go-live condition. `decisions.md` and
  `CLAUDE.md` both still said "missing from the report's plan" — corrected to
  note it's since been adopted, while flagging it's still not done in this
  repo's `eval/testset.yaml` (still 50 queries).
- **OCR of the scanned Erlasse is still not budgeted** in the report's roadmap
  (finding 4, session 001) — checked again, no mention of OCR anywhere in
  v4.1. That finding still stands as open.
- **§5.6–5.7 narrate a completed departmental pilot** — private LLM on ITS
  Schwyz infrastructure (REQ-07 met), 72 live parking queries, pseudonymised
  logging in production (REQ-08 met) — that this repository does not
  implement. This repo stays at the earlier technical-prototype stage: Gemini
  via external API, no live citizen traffic. Added a note to `CLAUDE.md` and
  `FOLDER-DESCRIPTION.md` so a future session doesn't read those report
  sections as a description of what's in this codebase.

Everything else checked against the report — the confidence formula and
weights, S2's dominance, the REQ-11 wording in Table 4, the `0.82` threshold
status, the error-handling rationale — still matches both the code and
`decisions.md` with no changes needed.

## 4. Coverage check (REQ-11) — how it works, for the record

Answered in chat in detail; summarized here since it's the kind of mechanism
`decisions.md` exists to carry forward.

- `config.yaml` → `coverage.rules`: three topics (`gebuehren`, `parkkarte`,
  `rechtsgrundlage`), each with keyword patterns and a set of required
  `doc_type`s.
- `src/coverage.py::classify_topics` — lowercases the query, keeps every rule
  whose keyword appears as a substring.
- `src/coverage.py::check` — intersects each matched rule's required doc types
  against the `doc_type`s actually present in the retrieved chunks; any rule
  with an empty intersection goes into `missing`.
- Wired into `src/pipeline.py::answer_query` after generation, before routing;
  `src/routing.py::decide` checks `coverage["passed"]` before the confidence
  threshold, independent of C.
- **Known weakness, not yet tested:** detection is keyword-only. A fee question
  phrased without any of the twelve `gebuehren` patterns matches no rule and
  triggers nothing. This is exactly what the report's planned negative-control
  test (de-index a document, see if REQ-11 catches it — §7.3, Gate 1) needs to
  probe with varied phrasing, not just one canonical query.

Produced `REI_Backup_B17_Abdeckungspruefung_DE.pptx` — a standalone backup
slide (styled to match the deck's existing B13/B14) explaining the rule table
and why the confidence score can't substitute for it. Not yet merged into the
executive deck itself (that file was open in PowerPoint during the session).

## 5. Left open

- Everything from 001 §8 (eval chain never run, `calibrated_threshold` null,
  no PM4 result figures) — untouched this session.
- OCR budgeting gap (finding 4) — still not in the report's roadmap.
- B17 backup slide exists as a separate file, not yet appended to
  `REI_Executive_Presentation_D15_v10_DE.pptx`.
- The `RAG Project/` outer folder has no single current-file convention — six+
  report/plan variants coexist loose at top level plus in `_RAG_withPilot/`
  and `history/`. Worth the user doing a cleanup pass; not this repo's job to
  fix, but worth a session reading `../` fresh each time rather than trusting
  a remembered path.
