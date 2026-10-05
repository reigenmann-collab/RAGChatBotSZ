# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

German-language RAG assistant for Gemeinde Schwyz road-traffic and parking inquiries — coursework prototype for milestone **PM4** of the AIBS project. The governing spec is `../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`; many design choices trace to numbered requirements in it (REQ-xx, §4.3, §4.4). When code and report disagree, surface it to the user rather than quietly fixing either.

Deployed: https://ragchatbotsz-4gfjul5ikk4khr3wotj9s8.streamlit.app/ · Repo: https://github.com/reigenmann-collab/RAGChatBotSZ

## Start here

Invoke the `pm4-project-context` skill before substantive work, or at minimum read `PROGRESSION/INDEX.md` (current state) and the latest `PROGRESSION/` entry. The skill's `references/decisions.md` explains choices that look like bugs until you know why.

## Commands

There is no test suite, linter, or build step. Run everything from the repo root (scripts add `src/` to `sys.path` themselves). Local key goes in `.env` (`GEMINI_API_KEY`, copy `.env.example`).

```bash
pip install -r requirements.txt

# Corpus → index (rebuild + re-commit data/index/ if the corpus changes)
python src/ingest.py        # fetch sources listed in config.yaml → data/raw/
python src/ocr.py           # transcribe scanned Erlasse (needs API key; cached)
python src/chunk_index.py   # chunk + embed locally → data/index/

# Run
python src/pipeline.py "Was kostet eine Gewerbeparkkarte?" [--json]   # one query, end to end
streamlit run app/streamlit_app.py                                    # demo UI on :8501

# Evaluation chain (never yet run end to end)
python eval/run_eval.py [--limit 5]     # --limit = smoke test; records every signal per query
python eval/label.py                    # machine pre-labels + eval/results/review_sheet.csv
# caseworker fills LABEL_SACHBEARBEITUNG, then:
python eval/label.py --merge
python eval/calibrate.py --apply        # derives threshold, writes it into config.yaml
python eval/report_results.py           # → eval/results/pm4_results.md
```

`PM4_MODEL` in `.env` overrides `generation.model` from `config.yaml`. `refresh_folder_description.py` (under `.claude/skills/pm4-project-context/scripts/`) regenerates the skill's folder map after layout changes.

## Architecture

`src/pipeline.py::answer_query` is the spine; the order of its steps is load-bearing:

1. **Hard routing first** (`routing.is_hard_routed`) — legal disputes/appeals return *before retrieval or generation*, with only an escalation summary. The report requires "no automated answer attempt"; generating then discarding would miss the point.
2. `retrieve` (FAISS over local ONNX embeddings) → `generate_answer` (German, cited, JSON-schema output).
3. **Two independent checks on the draft:** `coverage.check` (REQ-11: fee/permit questions must retrieve a document of the required `doc_type`) and `confidence.score` (composite `C = w₁S₁ + w₂S₂ + w₃S₃`: retrieval similarity, claim-by-claim grounding via a second LLM call, model self-assessment). Coverage is deliberately **not** folded into `C` — completeness and correctness are different properties.
4. `routing.decide` combines them; escalations get an LLM-written summary (REQ-03); every query is written to the pseudonymised audit log.

Things only visible across files:

- **`config.yaml` is the control plane.** Corpus sources (each with a `doc_type` and optional `indexable: false`), model names, token budgets, confidence weights, threshold, coverage rules, and hard-route terms all live there. The `doc_type` assigned to a source is what REQ-11 keys on, so retyping a document changes routing behaviour.
- **`src/llm.py::structured()` is the only text-generation entry point.** `generate.py`, `confidence.py`, and `eval/label.py` all call it; its `tool_name` arg is unused (kept from the earlier Anthropic tool-use interface). Swapping providers means touching `llm.py` and `config.py` only. It retries transient `ServerError`s; the Streamlit app catches `ServerError`/`ClientError` separately from a catch-all.
- **Indexing writes two parallel artefacts** — `data/index/corpus.faiss` and `chunks.jsonl` — matched by position. Chunks carry `embed_text` (title-prefixed, used for embedding) and `text` (clean, used for generation).
- **`eval/run_eval.py` stores raw signals (S1/S2/S3/coverage) for every query**, not just the routing outcome, so `calibrate.py` can sweep thresholds offline. `label.py` must label *every generated* row including escalated ones — labelling only auto-answered rows censors the calibration sample. `calibrate.py --apply` edits the literal line `calibrated_threshold: null` in `config.yaml`.
- **`active_threshold()`** returns `calibrated_threshold` if set, else the `0.82` placeholder. The report is explicit that the placeholder is not a calibrated value.

## Guardrails

- **Don't switch embeddings to the German-native Jina model** — its ONNX build emits NaN vectors under this onnxruntime/Python build (FAISS then returns `-3.4e38` for everything). MiniLM-multilingual is a deliberate fallback.
- **No blank lines inside an injected `<style>` block** in `app/streamlit_app.py` — a blank line ends Streamlit's raw-HTML markdown block and the remaining CSS renders as visible text. `inject_css()` strips them.
- **Before swapping the Gemini model**, check the grounding step (S2) still marks a fabricated price and an invented validity claim as `nicht_gedeckt`; speed alone isn't the bar. `gemini-3.6-flash` is a reasoning model that needs inflated `max_tokens` (`thinking_budget=0` is rejected).
- **Git:** `data/index/` is committed on purpose (the deployed app needs it); `data/raw/`, `data/logs/`, `eval/results/` are ignored on purpose. Streamlit Cloud takes the key from Secrets (same `os.getenv` path) and auto-deploys on push to `main` — if a change doesn't appear, hard-refresh the browser before debugging.
- `.devcontainer/` came from GitHub's web UI (Python 3.11); local and Cloud run 3.14. Don't treat it as the canonical environment.

## Open thread

The milestone has code but not evidence: the eval chain above has never been run, `calibrated_threshold` is still `null`, and there are no PM4 result figures. Until the caseworker review sheet is merged, any figure is provisional (report §5.6).

## Before finishing a session

If anything changed, add a `PROGRESSION/NNN-slug.md` entry and an `INDEX.md` row; update `references/decisions.md` if a standing decision changed.
