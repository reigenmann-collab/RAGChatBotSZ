---
name: pm4-project-context
description: Project memory for the PM4 Community RAG Chatbot prototype — the Gemeinde Schwyz road-traffic and parking assistant built for the AIBS exam project. Carries the session progression log, the folder map, and the standing technical decisions. Use this at the start of any session that touches this repository, and whenever the user asks what was done before, what state the prototype is in, where something lives, why something was built a particular way, or asks to continue or resume work. Use it before changing the model, the embedding model, the corpus, the confidence scoring, the routing rules, the evaluation harness, or the Streamlit demo — those areas carry non-obvious decisions that were expensive to discover and are easy to undo by accident. Also use it when the user mentions Gemeinde Schwyz, Gewerbeparkkarte, Parkkarte, Strassenverkehr, the PM4 milestone, the AIBS report, Streamlit Cloud deployment, or the RAGChatBotSZ repo, even if they do not name this skill.
---

# PM4 project context

This repository is the working prototype for **PM4 — Departmental Pilot (Traffic
Department)** of the *Community RAG Chatbot for Citizen Inquiries* project: a
German-language RAG assistant answering road-traffic and parking questions for
Gemeinde Schwyz, grounded strictly in published municipal documents.

It is coursework for the AIBS programme (Swiss Cyber Institute), so the
governing document is not a ticket or a README — it is the written project
report one directory up:
`../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`. When the
code and that report disagree, that is a finding worth surfacing to the user,
not a bug to quietly paper over. Several such disagreements already exist and
are recorded.

## Read these first

Load them in this order. Together they cost little and prevent the two failure
modes that actually hurt here: re-deriving state that is already written down,
and undoing a decision whose reasoning is not visible in the code.

1. **`PROGRESSION/INDEX.md`** — what has happened, newest first, and the current
   state in one paragraph. Then read the most recent numbered entry in full.
2. **`references/FOLDER-DESCRIPTION.md`** — what every file and directory is for,
   and which ones are deliberately not committed.
3. **`references/decisions.md`** — standing decisions and the reasoning behind
   them. Read this before changing anything in the pipeline, the model choice,
   or the demo. Most entries exist because the obvious-looking alternative was
   tried and failed.

## The shape of the thing

```
ingest.py → ocr.py → chunk_index.py → [ retrieve → generate →
            coverage + confidence → routing → auditlog ] = pipeline.py
```

Retrieval and embeddings run locally (ONNX + FAISS); only generation and the
grounding check call an external API. The architecture is not generic RAG — it
implements specific requirements from the report, and the parts that look like
overengineering are usually the parts carrying a requirement:

- **Composite confidence** `C = w₁S₁ + w₂S₂ + w₃S₃` (report §4.3). S2
  (answer–source grounding) carries the largest weight because grounding failure
  is the worst failure mode for a public authority. S3 (model self-assessment)
  is a weak third signal and never decisive.
- **REQ-11 coverage check** is deliberately *not* part of C. An answer can be
  fully grounded and still omit material information from a document that was
  never retrieved. Completeness and correctness are different properties.
- **Two independent routing mechanisms** (§4.4). Topic-based hard routing (legal
  disputes, appeals) runs *before* generation — nothing is generated at all.
  Confidence escalation is separate. Collapsing them would let a confidently
  answered legal question reach a citizen, which is the outcome the whole design
  exists to prevent.
- **The threshold is derived, not chosen.** `calibrate.py` fits it from labelled
  results. The `0.82` currently in play is a placeholder the report explicitly
  disowns.

## Keeping this current

The value of this skill decays fast if it is not maintained, and a stale
progression log is worse than none — it will be trusted.

**At the end of a session that changed something**, add an entry to
`PROGRESSION/` (next number, short slug) and a row in `PROGRESSION/INDEX.md`.
Record decisions and their *reasons*, bugs and their *root causes*, and state
honestly what was left unfinished. Update the "current state" paragraph in
`INDEX.md`.

**If the folder layout changed**, refresh the map rather than hand-editing it:

```bash
python .claude/skills/pm4-project-context/scripts/refresh_folder_description.py
```

The script regenerates the inventory (tree, sizes, git state, index stats) and
preserves the hand-written explanations above it, so the prose survives.

**If a standing decision changed**, update `references/decisions.md` — including
why it changed. An entry that quietly disappears looks like an oversight to the
next session.

## Things that will bite you

Full detail in `references/decisions.md`; these are the ones worth knowing before
you touch anything.

- **Do not "upgrade" the embedding model to the German-native Jina model.** It
  emits NaN vectors under this onnxruntime/Python build. The weaker multilingual
  MiniLM is a deliberate fallback.
- **Never put a blank line inside an injected `<style>` block** in the Streamlit
  app. It terminates Streamlit's raw-HTML markdown block and the rest of the CSS
  renders as visible text on the page.
- **`data/index/` is committed on purpose**; `data/raw/`, `data/logs/` and
  `eval/results/` are ignored on purpose.
- **The API key lives in `.env` locally and in Streamlit Cloud's Secrets
  manager** — never in the repo. Streamlit Cloud injects it as an environment
  variable, so no code change is needed between local and deployed.
- **Streamlit Cloud auto-deploys on push to `main`.** There is no separate
  publish step. If a change appears not to land, suspect a stale browser page
  first — hard refresh before debugging anything else.
- **Before swapping the Gemini model**, run the grounding-quality check described
  in `decisions.md`: the model must catch a fabricated price and an invented
  validity claim as `nicht_gedeckt`. Speed is not the only criterion; S2 is the
  safety mechanism.

## The open thread

The evaluation chain has never been run end to end, so the milestone has code
but not yet evidence. If the user asks what to do next, this is it:

```bash
python eval/run_eval.py
python eval/label.py
# caseworker fills eval/results/review_sheet.csv, then:
python eval/label.py --merge
python eval/calibrate.py --apply
python eval/report_results.py
```

Note the honest caveat the report itself demands: until the caseworker review
sheet comes back, every figure is provisional, and the 50-query test set gives a
rule-of-three upper bound of 6.0% — not the ~2% the report requires before
go-live.
