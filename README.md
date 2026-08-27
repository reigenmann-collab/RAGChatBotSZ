# PM4 — Departmental Pilot (Traffic Department)

Working prototype of the Community RAG Chatbot for milestone **PM4** of the
*Community RAG Chatbot for Citizen Inquiries* project (IT Services Schwyz,
AIBS written project report v2).

Domain: **road traffic and parking, Gemeinde Schwyz**. Answers in German,
grounded strictly in published municipal documents.

The prototype implements the architecture the report specifies rather than a
generic RAG demo. Specifically: the three-signal composite confidence score
(4.3), the independent REQ-11 coverage check, the two separate routing
mechanisms (4.4), auto-generated escalation summaries (REQ-03), pseudonymised
audit logging (REQ-08/09), and a calibration procedure that *derives* the
threshold instead of choosing one.

---

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and paste your Gemini API key:

```bash
cp .env.example .env
```

`.env` is git-ignored. The key is never logged and never written to disk by the
pipeline.

---

## Runbook

Run in order. Steps 1–2 are local and need no API key.

```bash
python src/ingest.py
```

Fetches the corpus defined in `config.yaml` — municipal web pages, the
Gewerbeparkkarten Merkblatt, and the road-traffic Erlasse — and writes one JSON
record per document to `data/raw/`. Respects `robots.txt` and rate-limits itself.

```bash
python src/ocr.py
```

Four of the five road-traffic Erlasse are **image-only scans with no text
layer**. This step extracts each page as a PNG and transcribes it with the
Gemini vision model, caching results so a re-run is free. Needs the API key.

```bash
python src/chunk_index.py
```

Chunks, embeds locally (ONNX, nothing leaves the machine at retrieval time) and
writes a FAISS index to `data/index/`.

```bash
python src/pipeline.py "Was kostet eine Gewerbeparkkarte?"
```

One query end to end, with signals, routing decision and sources.

```bash
streamlit run app/streamlit_app.py
```

The demo interface: citizen view on the left, pilot inspection view on the right.

---

## Evaluation and calibration

```bash
python eval/run_eval.py
python eval/label.py
```

`run_eval.py` runs all 50 test queries and records **every signal for every
query**, so thresholds can be swept offline without paying for another run.
`label.py` produces machine pre-labels plus
`eval/results/review_sheet.csv` — the sheet a Traffic Department caseworker
fills in.

> Report 5.6 requires caseworker review of every output. Until the sheet is
> completed and merged, all figures are **provisional**.

```bash
# caseworker fills column LABEL_SACHBEARBEITUNG, then:
python eval/label.py --merge
python eval/calibrate.py --apply
python eval/report_results.py
```

`calibrate.py` fits the weights (S2 constrained largest, per 4.3), plots the
score distribution and the precision/escalation sweep, and picks the **lowest**
threshold meeting the safety target — reporting the escalation rate as the
operational cost of that safety level. `--apply` writes the derived value into
`config.yaml`, superseding the `0.82` placeholder.

`report_results.py` writes `eval/results/pm4_results.md` with the
success-criteria table in the report's own format, including Wilson intervals
and the rule-of-three bound.

---

## Layout

```
config.yaml              corpus, weights, thresholds, coverage rules, hard-route terms
src/ingest.py            crawl + PDF/HTML extraction
src/ocr.py               vision OCR for the scanned Erlasse
src/chunk_index.py       chunking, local embeddings, FAISS
src/retrieve.py          top-k retrieval
src/generate.py          German answer + escalation summary (REQ-03)
src/confidence.py        S1 / S2 / S3 and the composite C (report 4.3)
src/coverage.py          REQ-11 coverage check
src/routing.py           hard routing + confidence escalation (report 4.4)
src/auditlog.py          pseudonymised audit log (REQ-08/09)
src/pipeline.py          orchestration
eval/testset.yaml        50 German queries with gold facts
eval/run_eval.py         batch run
eval/label.py            pre-label + caseworker review sheet
eval/calibrate.py        weight fitting + threshold derivation + figures
eval/report_results.py   PM4 results in report format
app/streamlit_app.py     demo interface
docs/                    scope decisions and corpus findings
```

---

## Known limitations

These are deliberate and documented rather than hidden. See
`docs/PM4_scope_and_corpus.md` for the full account.

- **REQ-07 is not met.** Answer generation calls an external API. Retrieval and
  embeddings are fully local, so only generation deviates — but the deviation is
  real and a production pilot would require a privately hosted model.
- **The corpus is small.** Gemeinde Schwyz publishes no parking ordinance, and
  issues no resident parking permits. The indexed corpus is 5 documents; it
  cannot support the 150-query test set report 5.3 requires before go-live.
- **Retrieval quality is limited** by a 384-dimension multilingual embedding
  model. The German-native model was the first choice but emits NaN vectors
  under this ONNX/Python build.
- **Two documents are excluded from the index** as cadastral maps whose only
  text is parcel numbers.
- **Labels are machine pre-labels** until the Traffic Department review sheet is
  returned.
