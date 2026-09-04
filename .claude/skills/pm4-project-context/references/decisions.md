# Standing decisions

Choices that are load-bearing but not visible from the code alone. Most exist
because the obvious alternative was tried and failed, or because a requirement in
the written report demands the non-obvious form.

If you change one of these, update the entry — including why. An entry that
silently vanishes reads as an oversight to the next session.

---

## Architecture

### The coverage check is not part of the confidence score
Report §4.3. An answer can be fully grounded in what was retrieved and still omit
material information held in a document that was never retrieved — the model is
legitimately confident, because what it saw does support what it said. No
confidence signal detects that. Completeness and correctness are different
properties, so REQ-11 is an independent routing trigger.

Verified on live data: *"Was kostet eine Gewerbeparkkarte?"* once retrieved only
`verordnung` chunks and escalated on coverage **at a composite of 0.9**.

### Hard routing runs before generation, not after
Report §4.4 requires legal disputes and appeals to reach a human "without an
automated answer attempt". Generating an answer and then discarding it would
satisfy the letter and miss the point. `pipeline.answer_query` therefore checks
hard-route patterns first and returns before retrieval.

Keeping this separate from confidence escalation is deliberate: collapsing them
would mean a *confidently* answered legal question gets delivered automatically,
which is precisely the outcome the design exists to prevent.

### S2 carries the largest weight; S3 is never decisive
Retrieval similarity says relevant text was found, not that the answer is
correct. Model self-assessment is poorly calibrated exactly when the model is
confidently wrong (Guo et al. 2017; Kadavath et al. 2022). So grounding (S2)
dominates, and `calibrate.py` constrains the weight fit to keep it largest.

### "Incomplete" counts as a failure in calibration
Not a partial success. The PoC's own limitation was answers that were correct but
incomplete; scoring them as successes would calibrate the threshold against the
very failure mode REQ-11 exists to catch.

### Calibration labels every generated row, not just auto-answered ones
The escalated rows are exactly the ones the threshold has to separate. Labelling
only what passed routing would train the threshold on a censored sample. This was
a real bug, fixed — `label.py` labels `draft_answer`.

### The threshold is derived, not chosen
`calibrate.py` sweeps thresholds and picks the **lowest** one meeting the
precision target, then reports the resulting escalation rate as the operational
cost of that safety level. The `0.82` currently in `config.yaml` is a
**placeholder**; the report is explicit that a chosen threshold is not a
calibrated one. It stays a placeholder until the eval chain is run with
`--apply`.

---

## Models and embeddings

### Embedding model is `paraphrase-multilingual-MiniLM-L12-v2` — do not "fix" this
`jinaai/jina-embeddings-v2-base-de` was the first choice (German-native, better
suited). Its ONNX build **emits NaN vectors** under onnxruntime 1.29 / Python
3.14 — FAISS then returns `-FLT_MAX` sentinels for every query. The 384-dimension
multilingual MiniLM is a deliberate, verified fallback. Retrieval quality is
correspondingly weaker and is a documented limitation, not an oversight.

### Chunks are embedded with the document title prefixed
Mid-document chunks otherwise lose all trace of which document they came from,
which cost recall on queries naming the document ("Gewerbeparkkarte",
"Personalparkplatz"). `embed_text` carries the prefix; `text` stays clean for
generation.

### Current generation model: `gemini-3.1-flash-lite`
The path here matters, because each step ruled something out:

| Model | Why not / why |
|---|---|
| `gemini-2.5-flash` | Deprecated on this account (404; the API itself pointed to 3.6) |
| `gemini-3.6-flash` | Reasoning model — burns 200–500 tokens "thinking" before any output, and `thinking_budget=0` is **rejected** with a 400. Forced inflated `max_tokens`; ~12.8s round trips. |
| `gemini-3.5-flash-lite` | Fast, no thinking overhead, passed quality — then hit a Google-side 503 overload |
| `gemini-3.1-flash-lite` | **Current.** Stable through that outage, passed the same quality bar |

**Quality bar to reuse before swapping models.** Give the grounding checker an
answer containing a fabricated price (Fr. 200 against a source saying Fr. 150)
and an invented validity period, and require both to come back `nicht_gedeckt`.
Speed alone is not sufficient — S2 *is* the safety mechanism, so a faster model
that grades leniently is a downgrade.

### Structured output uses Gemini's native JSON schema
`response_mime_type="application/json"` + `response_json_schema`. The
`structured()` signature in `src/llm.py` still takes a `tool_name` argument,
unused, so callers written against the earlier Anthropic forced-tool-use
interface did not have to change. `generate.py`, `confidence.py` and
`eval/label.py` are untouched by the migration.

---

## Corpus

### Two documents are excluded from the index on purpose
`gewerbeparkkarten_plan` and `erlass_4_21` are cadastral maps. The first *does*
have a text layer — 58,000 characters of parcel numbers and street labels with no
answerable content. Indexing it would add spurious high-similarity matches and
inflate S1 on queries it cannot answer. Both stay in the manifest as documented
ingestion gaps (`indexable: false`).

### The Parkplätze web page is typed `gebuehrentarif`
Because it *is* the fee schedule — the tariffs exist nowhere else, certainly not
in any ordinance. That typing is what lets REQ-11 require a fee document for fee
questions. It is a corpus-governance decision, not a workaround.

### Four ordinances need OCR
4.20, 4.21, 4.25 and 4.75 are image-only scans. `ocr.py` transcribes them via the
vision model and caches results, so re-runs are free. The report's roadmap does
not budget for this — flagged as a Gate 1 finding.

### HTML extraction strips the CMS chrome
The i-web CMS renders login, search and breadcrumb markup *inside* the content
column — roughly 2,600 identical characters per page. Left in, it pulls unrelated
chunks toward each other and dilutes retrieval. Hence `.content-container` plus
targeted `decompose()` calls in `ingest.py`.

---

## Repository and deployment

### `data/index/` is committed; `data/raw/`, `data/logs/`, `eval/results/` are not
The prebuilt FAISS index ships so the deployed app works without re-running
ingestion, OCR and embedding on first load. It is public municipal data, not a
secret, and it is small. Raw scrapes are regenerable; logs are runtime data;
eval results are per-run.

If the corpus changes, rebuild and re-commit:
`python src/ingest.py && python src/ocr.py && python src/chunk_index.py`

### The API key is never in the repo
`.env` locally (gitignored), Streamlit Cloud **Secrets** in deployment. Cloud
injects secrets as environment variables, which `os.getenv("GEMINI_API_KEY")` in
`src/config.py` reads unchanged — so no code differs between local and deployed.
`.streamlit/secrets.toml` is pre-emptively gitignored too.

### Streamlit Cloud auto-deploys on push to `main`
There is no separate publish step. When a pushed change appears not to have
landed, the cause has so far always been a **stale browser page** — hard refresh
before debugging. "Reboot app" from the Manage app menu forces a fresh clone.

### The demo is styled after gemeindeschwyz.ch deliberately
So a demo to the department reads as "this could sit on our portal" rather than
"this is a developer tool". Tokens came from the site's compiled CSS, not from a
screenshot: primary red `#e10a12`, navy `#050924`, Source Sans Pro body (already
Streamlit's default), Barlow for the wordmark and headings.

### Never put a blank line inside an injected `<style>` block
A blank line ends Streamlit's raw-HTML markdown block (CommonMark rule) and
everything after it renders as literal visible text. `inject_css()` keeps blank
lines in the source for readability and strips them before rendering.

### The inspection column is toggleable
Sidebar toggle "Prüfansicht anzeigen", default on. Off hides the right column,
the suppressed draft answer, and the caseworker escalation summary — all
staff-facing content a citizen would never see.

---

## Error handling

### Gemini errors are caught by class, not swallowed generically
`ServerError` (transient 5xx) gets a "try again shortly" message and is retried
in `llm.py` with backoff; `ClientError` (4xx — bad key, quota) gets a different
message because retrying will not help; a catch-all prevents any raw traceback
reaching a demo audience. Details go to stdout, which Streamlit Cloud captures in
its logs.

This exists because only `RuntimeError` was caught originally, and a live 503
dumped a full stack trace onto the page.

---

## Known non-compliance, stated openly

- **REQ-07 (Swiss infrastructure) is not met.** Retrieval and embeddings are
  local; generation calls an external API. A production pilot would need a
  privately hosted model. This was a deliberate prototype trade-off.
- **REQ-06 (<5s) is not met.** ~7–12s per query — two sequential API calls
  (generation, then the grounding check).
- **The 150-query gate cannot be met on this corpus.** The test set is 50 →
  rule-of-three upper bound 6.0%. Expanding the corpus is a prerequisite for
  expanding the test set, and that dependency is missing from the report's plan.
