# PM4 Prototype — Session Recap

**Project:** Community RAG Chatbot for Citizen Inquiries — milestone **PM4, Departmental Pilot (Traffic Department)**
**Municipality:** Gemeinde Schwyz · German only · road traffic and parking
**Recap written:** 2026-10-03 (covers the build session 2026-08-26 → 2026-09-04)
**Live demo:** https://ragchatbotsz-4gfjul5ikk4khr3wotj9s8.streamlit.app/
**Repo:** https://github.com/reigenmann-collab/RAGChatBotSZ (`main`, auto-deploys to Streamlit Cloud)
**Governing spec:** `../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`

Full detail lives in [`PROGRESSION/001-prototype-build-and-deploy.md`](../PROGRESSION/001-prototype-build-and-deploy.md)
and `.claude/skills/pm4-project-context/references/decisions.md`. This file is the short version.

---

## 1. Status at a glance

| Area | State |
|---|---|
| Pipeline (ingest → OCR → index → retrieve → generate → confidence/coverage → routing → audit log) | Built, verified live |
| Corpus | 7 documents, 36 chunks (parking permits widened to adjacent road-traffic Erlasse) |
| Streamlit demo | Deployed, styled after gemeindeschwyz.ch |
| LLM backend | Gemini (`gemini-3.1-flash-lite`), migrated from Anthropic mid-session |
| Evaluation chain | Code complete, **never run end to end** |
| Operating threshold | **0.82 placeholder** — `calibrated_threshold` is still `null` in `config.yaml` |
| PM4 result figures | None yet |

**One-line summary:** the milestone has code but not yet evidence.

---

## 2. What was built

```
ingest.py → ocr.py → chunk_index.py → [ retrieve → generate →
            coverage + confidence → routing → auditlog ] = pipeline.py
```

- **Retrieval/embeddings local** (ONNX + FAISS, inner product on L2-normalised vectors = cosine). Only generation and the grounding check call an external API.
- **Composite confidence** `C = w₁S₁ + w₂S₂ + w₃S₃` (report §4.3): S1 retrieval strength, S2 answer–source grounding (largest weight), S3 model self-assessment (weak, never decisive).
- **REQ-11 coverage check** is deliberately *outside* `C` — a grounded answer can still miss material information from an un-retrieved document.
- **Two independent routing mechanisms** (§4.4): hard routing for legal disputes/appeals runs *before* generation; confidence escalation is separate.
- **Audit log** (REQ-08/09): salted SHA-256 pseudonyms, raw query never written.
- **Evaluation harness** (`eval/`): 50-query German test set (32 realistic + 18 synthetic) → `run_eval.py` → `label.py` → `calibrate.py` → `report_results.py`.
- **Demo** (`app/streamlit_app.py`): citizen view left, pilot inspection right, sidebar toggle to hide the staff-facing column.

---

## 3. Corpus findings that contradict the written report

The most valuable output of the session. Full write-up in `docs/PM4_scope_and_corpus.md`.

1. **No municipal parking ordinance exists.** Of 68 Erlasse, only *1.45 Personalparkplätze* touches parking, and it is internal (staff).
2. **The municipality issues no resident parking permits** — only *Gewerbeparkkarten*. The report's §3.3 "second residential permit" example has no factual basis. *Correct in the report.*
3. **The fee schedule is a web page, not an ordinance** (ten car parks, Parkplätze page). Reproduces the PoC's own §5.6 failure mode; hence `doc_type: gebuehrentarif` so REQ-11 can require it.
4. **Four of five road-traffic Erlasse are image-only scans** (4.20, 4.21, 4.25, 4.75). OCR is required but not budgeted in report §7.4 or the §7.5 refresh. *Add to the Gate 1 checklist.*
5. **The corpus cannot support the 150-query gate** (§5.3). 50 queries → rule-of-three upper bound **6.0%**, not ~2%. *Report as not met; corpus expansion is an unplanned prerequisite.*

Live proof REQ-11 works: *"Was kostet eine Gewerbeparkkarte?"* retrieved only `verordnung` chunks and escalated on coverage **at composite 0.9**.

---

## 4. Key decisions (and why)

| Decision | Reason |
|---|---|
| Embeddings: `paraphrase-multilingual-MiniLM-L12-v2` | The German-native Jina model emits **NaN vectors** under onnxruntime 1.29 / Python 3.14. Do not "upgrade". |
| Generation: `gemini-3.1-flash-lite` | `2.5-flash` deprecated; `3.6-flash` is a slow reasoning model (`thinking_budget=0` rejected); `3.5-flash-lite` hit a 503 overload. |
| Model quality gate | Grounding checker must flag a fabricated price (Fr. 200 vs 150) and an invented validity period as `nicht_gedeckt`. S2 is the safety mechanism. |
| Threshold is derived | `calibrate.py` picks the lowest threshold meeting the precision target; 0.82 is a disowned placeholder. |
| "Incomplete" = failure in calibration | Scoring it as success would calibrate against the exact failure REQ-11 exists to catch. |
| Calibration labels all generated rows | Escalated rows are what the threshold must separate; labelling only auto-answered rows censors the sample. |
| Two docs excluded from index | `gewerbeparkkarten_plan` and `erlass_4_21` are cadastral maps — noise that would inflate S1. |
| `data/index/` committed; `data/raw/`, `data/logs/`, `eval/results/` ignored | Deployed app needs the prebuilt index; the rest is regenerable or runtime. |
| API key never in repo | `.env` locally, Streamlit Cloud Secrets in deployment (same `os.getenv` path). |

---

## 5. Bugs found and fixed

| Symptom | Root cause |
|---|---|
| All retrieval scores `-3.4e38` | Jina ONNX NaN vectors → MiniLM fallback |
| CSS rendered as visible text | Blank line inside injected `<style>` ends Streamlit's raw-HTML block |
| ~2,600 chars of site chrome per chunk | i-web CMS renders nav/login inside the content column → `.content-container` + `decompose()` |
| Hard-route pattern `busse` never matched | A Cyrillic `е` in the pattern |
| "Wer haftet dafür?" not hard-routed | `haftet` inflection missing |
| Calibration on wrong rows | `label.py` labelled only auto-answered rows; now labels `draft_answer` |
| Raw traceback on Gemini 503 | Only `RuntimeError` was caught; now `ServerError`/`ClientError`/catch-all + backoff retry |
| Test-set count said 48, was 50 | Corrected; bound recomputed to 6.0% |

---

## 6. Known non-compliance (stated openly)

- **REQ-07 (Swiss infrastructure):** not met by design — generation calls an external API.
- **REQ-06 (<5 s):** not met — ~7–12 s per query (two sequential API calls).
- **150-query gate:** cannot be met on this corpus (see §3.5).

---

## 7. Next steps

The open thread is **evidence, not code**:

```bash
python eval/run_eval.py
python eval/label.py
# caseworker fills eval/results/review_sheet.csv, then:
python eval/label.py --merge
python eval/calibrate.py --apply
python eval/report_results.py
```

Until the caseworker review sheet comes back, every figure is provisional by the report's own standard (§5.6).

Beyond the eval chain:
- Feed the five corpus findings back into the written report (esp. the §3.3 example and the Gate 1 checklist).
- Decide how to handle the 150-query gap: report as unmet, or expand the corpus first.
- Longer term: privately hosted model (REQ-07) and a latency fix (REQ-06).
