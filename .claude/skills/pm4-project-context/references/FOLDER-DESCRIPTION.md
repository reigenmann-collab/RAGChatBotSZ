# Folder map

What each thing in this repository is for. The prose below is hand-written; the
inventory at the bottom is generated — refresh it with
`python .claude/skills/pm4-project-context/scripts/refresh_folder_description.py`
rather than editing it by hand.

## Where this sits

The repository is `Prototype_PM4/`, one folder inside the wider coursework tree.
That outer tree churns constantly (the report alone has gone through v2 → v3.9
→ v4.0 → v4.1, EN → DE, and been renamed and moved more than once) — do not
trust a cached file name here; re-list `../` if a path 404s. As of 2026-10-15:

```
RAG Project/
├── _RAG_withPilot/
│   └── REI_Community-RAG-Chatbot_AIBS_Projektbericht_v4_1_DE.docx   ← the spec (current)
├── history/                         superseded report versions (e.g. the old v2)
├── MS-0 … MS-5/                     course milestone submissions
├── error-handling/                  saved Streamlit Cloud logs
└── Prototype_PM4/                   ← this repo (git, deployed)
```

The `.docx` report is the authority on requirements, metrics and milestone
boundaries. Read it (or the extracts in `docs/`) before arguing with a design
choice — most of them trace back to a numbered requirement. Its narrative in
§5.6–5.7 describes a fully realised departmental pilot (private LLM on ITS
Schwyz, REQ-07 met) that goes beyond what this repo implements — that is the
report's case-study target state, not a claim about this codebase.

## Top level

| Path | What it is |
|---|---|
| `config.yaml` | Single source of truth for corpus sources, doc types, retrieval params, model names, confidence weights, threshold, coverage rules, hard-route terms, logging, targets. Most behaviour changes belong here, not in code. |
| `requirements.txt` | Python deps. Streamlit Cloud installs from this. |
| `README.md` | Human-facing setup and runbook. |
| `.env` | **Not committed.** Local `GEMINI_API_KEY`. In deployment the key comes from Streamlit Cloud Secrets instead. |
| `.env.example` | Template showing the expected variables. |
| `.streamlit/config.toml` | Theme tokens matching gemeindeschwyz.ch (red `#e10a12`, navy `#050924`). |
| `.claude/launch.json` | Dev-server config so the app can be started as a preview. |
| `.claude/skills/pm4-project-context/` | This skill. |
| `.devcontainer/` | Added via GitHub's web UI; not used by the local workflow. |
| `PROGRESSION/` | Session history. Start here when resuming. |
| `docs/PM4_scope_and_corpus.md` | The corpus findings — including the ones that contradict the written report. |

## `src/` — the pipeline

Execution order, not alphabetical:

| File | Role |
|---|---|
| `config.py` | Loads `config.yaml` + `.env`; resolves API key and model name. |
| `ingest.py` | Crawls the corpus. Robots-respecting, rate-limited. Renders HTML tables as pipe-delimited text so the tariff table survives. Strips CMS chrome. |
| `ocr.py` | Transcribes the four image-only scanned Erlasse via the vision model. Caches to `data/raw/*.ocr.json`, so re-runs cost nothing. |
| `chunk_index.py` | Paragraph-aware chunking, local ONNX embeddings, FAISS index. Embeds with the document title prefixed. |
| `retrieve.py` | Top-k lookup; returns chunks with cosine similarity. |
| `llm.py` | Gemini wrapper. `structured()` for JSON-schema output, `vision_transcribe()` for OCR, plus the retry pass for transient 5xx. |
| `generate.py` | German answer with mandatory citations, and the REQ-03 escalation summary. |
| `confidence.py` | S1 / S2 / S3 and the composite `C`. |
| `coverage.py` | REQ-11 coverage check — independent of `C`. |
| `routing.py` | Hard routing + confidence escalation, kept separate on purpose. |
| `auditlog.py` | REQ-08/09 pseudonymised audit log (salted SHA-256; raw query never written). |
| `pipeline.py` | Orchestration, and a CLI for one-off queries. |

## `eval/` — the evidence chain

Run in order. **Has never been run end to end** — this is the main open thread.

| File | Role |
|---|---|
| `testset.yaml` | 50 German queries (32 realistic, 18 synthetic) with gold facts and expected routing. |
| `run_eval.py` | Runs the pipeline over the set, recording **every signal for every query** so thresholds can be swept offline without paying for another run. |
| `label.py` | Machine pre-labels + a caseworker review sheet (`--merge` folds the human labels back in). Report §5.6 requires that human review; figures before it are provisional. |
| `calibrate.py` | Fits the weights (S2 constrained largest), sweeps thresholds, picks the lowest meeting the precision target, writes figures. `--apply` writes the derived threshold into `config.yaml`. |
| `report_results.py` | PM4 results tables in the report's own format, with Wilson intervals and the rule-of-three bound. |

## `app/`

`streamlit_app.py` — the demo. Citizen view left, pilot inspection right, with a
sidebar toggle to hide the inspection column entirely for citizen-facing demos.
Styled after gemeindeschwyz.ch.

## `data/`

| Path | Committed? | Why |
|---|---|---|
| `data/index/` | **Yes** | Prebuilt FAISS index + chunks, so the deployed app works without re-running ingestion, OCR and embedding on first load. Public municipal data, small. |
| `data/raw/` | No | Regenerable by `ingest.py` + `ocr.py`. |
| `data/logs/` | No | Runtime audit log. |
| `eval/results/` | No | Per-run output. |

<!-- BEGIN GENERATED INVENTORY -->

*Generated 2026-10-15 by `refresh_folder_description.py`.*

## Repository state

- Branch: `main`
- HEAD: `c81187f Expand CLAUDE.md with commands and pipeline architecture`
- Remote: https://github.com/reigenmann-collab/RAGChatBotSZ.git
- Working tree: has uncommitted changes

## Built index

- 7 documents, 36 chunks
- Doc types: dienstleistung, gebuehrentarif, merkblatt, verordnung
- Embeddings: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384d)

## Tracked files

| Path | Size |
|---|---|
| `.claude/launch.json` | 253 B |
| `.claude/skills/pm4-project-context/SKILL.md` | 6.9 KB |
| `.claude/skills/pm4-project-context/references/FOLDER-DESCRIPTION.md` | 7.3 KB |
| `.claude/skills/pm4-project-context/references/decisions.md` | 9.7 KB |
| `.claude/skills/pm4-project-context/scripts/refresh_folder_description.py` | 5.2 KB |
| `.devcontainer/devcontainer.json` | 1.0 KB |
| `.env.example` | 376 B |
| `.gitignore` | 420 B |
| `.streamlit/config.toml` | 410 B |
| `CLAUDE.md` | 7.1 KB |
| `PROGRESSION/001-prototype-build-and-deploy.md` | 12.3 KB |
| `PROGRESSION/INDEX.md` | 2.5 KB |
| `README.md` | 5.2 KB |
| `app/streamlit_app.py` | 19.9 KB |
| `config.yaml` | 7.7 KB |
| `data/index/chunks.jsonl` | 80.3 KB |
| `data/index/corpus.faiss` | 54.0 KB |
| `data/index/meta.json` | 329 B |
| `docs/PM4_scope_and_corpus.md` | 7.4 KB |
| `docs/SESSION_RECAP_fromCode_PM4 prototype status.md` | 7.0 KB |
| `eval/calibrate.py` | 10.5 KB |
| `eval/label.py` | 8.3 KB |
| `eval/report_results.py` | 9.1 KB |
| `eval/run_eval.py` | 4.1 KB |
| `eval/testset.yaml` | 16.5 KB |
| `requirements.txt` | 294 B |
| `src/auditlog.py` | 2.5 KB |
| `src/chunk_index.py` | 5.8 KB |
| `src/confidence.py` | 5.6 KB |
| `src/config.py` | 1.0 KB |
| `src/coverage.py` | 2.4 KB |
| `src/generate.py` | 6.2 KB |
| `src/ingest.py` | 6.2 KB |
| `src/llm.py` | 4.3 KB |
| `src/ocr.py` | 4.3 KB |
| `src/pipeline.py` | 6.0 KB |
| `src/retrieve.py` | 1.7 KB |
| `src/routing.py` | 2.9 KB |

## Present on disk but not committed

Deliberate - see `decisions.md`. Regenerable, runtime, or per-run output.

- **`data/raw/`** — `_manifest.json`, `erlass_1_45.json`, `erlass_4_20.json`, `erlass_4_20.ocr.json`, `erlass_4_21.json`, `erlass_4_25.json`, `erlass_4_25.ocr.json`, `erlass_4_75.json`, `erlass_4_75.ocr.json`, `gewerbeparkkarten.json`, `gewerbeparkkarten_merkblatt.json`, `gewerbeparkkarten_plan.json`, `parkplaetze.json`
- **`data/logs/`** — `audit.jsonl`
- **`eval/results/`** — *(empty)*

<!-- END GENERATED INVENTORY -->
