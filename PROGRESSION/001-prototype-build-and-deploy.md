# 001 — Prototype build, Gemini migration, deployment

**Dates:** 2026-08-26 → 2026-09-04
**Outcome:** Working PM4 prototype, live at
https://ragchatbotsz-4gfjul5ikk4khr3wotj9s8.streamlit.app/
**Repo:** https://github.com/reigenmann-collab/RAGChatBotSZ (branch `main`)

---

## 1. Starting point

The brief was to build a prototype for milestone **PM4 — Departmental Pilot
(Traffic Department)** of the *Community RAG Chatbot for Citizen Inquiries*
project, using the boundaries already fixed in
`../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`.

That report was read first and treated as the spec. It pins down more than a
generic RAG demo would: the three-signal composite confidence score (§4.3), the
REQ-11 coverage check, two *independent* routing mechanisms (§4.4), auto-generated
escalation summaries (REQ-03), pseudonymised audit logging (REQ-08/09), and a
calibration procedure that **derives** the threshold rather than choosing one.
The 0.82 threshold in the report is a PoC result; the 85% figure that appears in
earlier project documents is explicitly a dead planning placeholder.

Four scoping decisions were put to the user up front:

| Question | Chosen |
|---|---|
| Corpus domain | Keep **parking permits** (report §5.2 scope), widened to adjacent municipal road-traffic Erlasse |
| LLM backend | Anthropic API — **later changed to Gemini** (see §5) |
| Depth | Full evidence pack (pipeline + calibration + eval + UI) |
| Language | German only |

---

## 2. Corpus reconnaissance — the findings that mattered

Before writing code, the actual source data was checked. Several findings
contradict assumptions baked into the written report, and they are the most
valuable output of this session. Full write-up in
[`docs/PM4_scope_and_corpus.md`](../docs/PM4_scope_and_corpus.md).

1. **There is no municipal parking ordinance.** The Gemeinde Schwyz
   Erlasssammlung has 68 ordinances; none of them governs public parking. The
   only parking-specific Erlass is *1.45 Verordnung über Personalparkplätze* —
   staff parking, internal, not citizen-facing.

2. **The municipality issues no resident parking permits at all** (only
   *Gewerbeparkkarten* for tradespeople). Report §3.3 uses "a citizen asking
   whether they qualify for a second residential permit" as its decisive
   example — that inquiry has **no factual basis** in the real municipality.
   *This should be corrected in the report.*

3. **The fee schedule is a web page, not an ordinance.** Parking tariffs for ten
   car parks exist only on the Parkplätze content page. This reproduces the
   PoC's own failure mode (§5.6 — the un-indexed fee addendum) in live source
   data, and it is why that page carries `doc_type: gebuehrentarif` so REQ-11
   can require it.

4. **Four of the five road-traffic Erlasse are image-only scans** with no text
   layer (4.20, 4.21, 4.25, 4.75). Without OCR they cannot be retrieved at all.
   Report §7.4 Phase 1 budgets for indexing a fee addendum but *not* for OCR of
   the ordinance back-catalogue, and the monthly refresh in §7.5 has no
   procedure for a scanned document. *Recommend adding both to the Gate 1
   checklist.*

5. **The corpus cannot support the 150-query gate.** Report §5.3 requires ≥150
   domain queries before go-live. The indexed corpus does not contain that many
   distinct answerable questions. The test set is 50 → rule-of-three upper bound
   **6.0%**, not the ~2% the report wants. *Report this at the gate as not met;
   expanding the corpus is a prerequisite for expanding the test set, and that
   dependency is not currently in the plan.*

Verified live: the query *"Was kostet eine Gewerbeparkkarte?"* initially
retrieved only `verordnung` chunks, failed the coverage check, and escalated
**even at a composite score of 0.9**. REQ-11 fires on real data, unstaged.

---

## 3. What was built

Pipeline (`src/`), in execution order:

```
ingest.py  →  ocr.py  →  chunk_index.py  →  [ retrieve → generate →
              coverage + confidence → routing → auditlog ]  =  pipeline.py
```

- **`ingest.py`** — crawls the corpus in `config.yaml`; robots-respecting,
  rate-limited. Renders HTML tables as pipe-delimited text (losing the tariff
  table would lose the fee schedule).
- **`ocr.py`** — extracts each scanned page as PNG, transcribes via the vision
  model, caches to `data/raw/<id>.ocr.json` so re-runs are free.
- **`chunk_index.py`** — paragraph-aware chunking, local ONNX embeddings, FAISS
  inner-product index (vectors L2-normalised so inner product = cosine, which is
  what S1 is defined on).
- **`confidence.py`** — S1 retrieval strength, S2 answer–source grounding
  (entailment, largest weight), S3 model self-assessment (weak, never decisive).
- **`coverage.py`** — REQ-11. Independent of the composite score, because
  completeness and correctness are different properties.
- **`routing.py`** — hard routing (legal/appeals, evaluated *before* generation)
  and confidence escalation, deliberately separate.
- **`auditlog.py`** — salted SHA-256 pseudonyms; raw query never written.

Evaluation (`eval/`): `testset.yaml` (50 German queries with gold facts, 32
realistic + 18 synthetic) → `run_eval.py` → `label.py` (machine pre-labels +
caseworker review sheet) → `calibrate.py` (fits weights, derives threshold,
plots) → `report_results.py` (Wilson intervals + rule of three).

Demo (`app/streamlit_app.py`): citizen view left, pilot inspection right, with a
sidebar toggle to hide the inspection column for citizen-facing demos.

---

## 4. Demo restyled to match the source site

The demo was restyled to look like gemeindeschwyz.ch so a presentation to the
department reads as "this could sit on our portal" rather than "this is a
developer tool". Design tokens were pulled from the site's own compiled CSS,
not eyeballed:

- primary red `#e10a12`, dark navy `#050924`
- Source Sans Pro (body — already Streamlit's default), Barlow (wordmark/headings)
- the site's "Dokumente" table pattern reused for the sources list

---

## 5. Backend migration: Anthropic → Gemini

Requested mid-session. `src/llm.py` was rewritten to use `google-genai` with
Gemini's **native JSON response schema** (`response_json_schema`) instead of
Anthropic's forced tool-use. `generate.py`, `confidence.py` and `eval/label.py`
needed no changes — they only call the `structured()` interface.

Model selection churned, for reasons worth remembering:

| Model | Verdict |
|---|---|
| `gemini-2.5-flash` | Deprecated on this account (404, API itself pointed to 3.6) |
| `gemini-3.6-flash` | Works, but a reasoning model — spends 200–500 tokens "thinking" before any output, and `thinking_budget=0` is **rejected** (400). Needed inflated `max_tokens`. ~12.8s round trip. |
| `gemini-3.5-flash-lite` | Fast (~2–4s), no thinking overhead, passed the grounding-quality test. Adopted — then hit a Google-side **503 overload**. |
| **`gemini-3.1-flash-lite`** | **Current default.** Stable during the outage, passed the same grounding test. |

**Quality gate used for each candidate:** feed the grounding checker an answer
containing a fabricated price (Fr. 200 vs the true Fr. 150) and an invented
validity period, and require it to mark both `nicht_gedeckt`. Both flash-lite
models passed. Reuse this test before swapping models.

---

## 6. Deployment

`git init` → GitHub → Streamlit Community Cloud.

The key detail: **the API key is never in the repo.** `.env` is gitignored;
Streamlit Cloud's Secrets manager injects `GEMINI_API_KEY` as an environment
variable, which the existing `os.getenv` in `src/config.py` picks up unchanged.

`data/index/` **is** committed (small, public municipal data) so the deployed app
works without re-running ingestion/OCR/embedding on first load. `data/raw/`,
`data/logs/` and `eval/results/` stay ignored.

Streamlit Cloud auto-rebuilds on every push to `main` — there is no separate
"push to Streamlit" step. When a change appeared not to land, the cause was a
**stale browser page**; a hard refresh fixed it. A "Reboot app" from the Manage
app menu forces a fresh clone.

---

## 7. Bugs found and fixed

Recorded because each cost real time to diagnose and none is obvious from the code.

| Bug | Cause / fix |
|---|---|
| All retrieval scores `-3.4e38`, identical hits | `jinaai/jina-embeddings-v2-base-de` emits **NaN vectors** under onnxruntime 1.29 / Python 3.14. Switched to `paraphrase-multilingual-MiniLM-L12-v2` (384d, weaker but sound). |
| Half the CSS rendered as visible text | A **blank line inside a `<style>` block** ends Streamlit's raw-HTML markdown block (CommonMark). Blank lines are now stripped before injection. |
| ~2,600 chars of login/nav chrome in every page chunk | i-web CMS renders site chrome inside the content column. Fixed with `.content-container` + targeted `decompose()`. |
| Hard-route pattern never matched | A **Cyrillic `е`** had been typed in `"busse"`. |
| "Wer haftet dafür?" not hard-routed | Missing inflection — `haftet` added alongside `haftung`/`haftbar`. |
| Test set header said 48, actually 50 | Counts and the rule-of-three bound corrected (6.0%). |
| Calibration would have been trained on the wrong rows | `label.py` was labelling only auto-answered rows. Calibration needs **every generated** row — the escalated ones are exactly what the threshold must separate. Fixed to label `draft_answer`. |
| Raw traceback shown to demo audience on Gemini 503 | Only `RuntimeError` was caught. Now `ServerError` / `ClientError` / catch-all each produce a friendly German message; details go to server logs. Plus a retry pass with backoff in `llm.py`. |

---

## 8. State at end of session

**Working and verified live:** ingestion, OCR (3 scanned Erlasse transcribed),
indexing (36 chunks / 7 documents), retrieval, generation with citations,
grounding check, coverage check, hard routing with auto-summary, audit logging,
the Streamlit demo (local and deployed), error handling.

**Not yet done — the main open thread:**

- The evaluation chain has **never been run end to end.** `eval/results/` is
  empty. Consequently:
  - `calibrated_threshold` in `config.yaml` is still `null`; the app runs on the
    **0.82 placeholder**, which the report is explicit is not a calibrated value.
  - No PAA, safe-failure rate, or escalation-correctness figures exist yet.
  - The caseworker review sheet has not been produced or filled, so any figure
    produced before that is provisional by the report's own standard (§5.6).
- **REQ-06 not met:** ~7–12s per query against a 5s target (two sequential API
  calls — generation, then grounding).
- **REQ-07 not met by design:** generation calls an external API. Retrieval and
  embeddings are fully local.

**Next step, if resuming:** run
`eval/run_eval.py → label.py → calibrate.py --apply → report_results.py`.
That produces the derived threshold and the PM4 results tables, which is the
actual milestone evidence.
