# PM4 — Community RAG Chatbot (Gemeinde Schwyz)

German-language RAG assistant for municipal road-traffic and parking inquiries.
Coursework prototype for milestone **PM4** of the AIBS project; the governing
spec is `../REI_Community-RAG-Chatbot_AIBS_Written_Project_Report_v2.docx`.

Deployed: https://ragchatbotsz-4gfjul5ikk4khr3wotj9s8.streamlit.app/ ·
Repo: https://github.com/reigenmann-collab/RAGChatBotSZ

## Start here

**Invoke the `pm4-project-context` skill** before doing substantive work in this
repository. It carries the session history, the folder map, and the standing
technical decisions — all of which exist because re-deriving them costs a lot of
time, and because several look like bugs until you know why they are that way.

Minimum orientation if you do nothing else: read `PROGRESSION/INDEX.md` for the
current state and the most recent entry for how it got there.

## Guardrails worth knowing immediately

These have each already been learned the hard way once:

- **Do not switch the embedding model to the German-native Jina model.** It emits
  NaN vectors under this onnxruntime/Python build. The weaker multilingual
  MiniLM is a deliberate fallback.
- **Never leave a blank line inside an injected `<style>` block** in the
  Streamlit app — it ends Streamlit's raw-HTML block and the CSS renders as
  visible text.
- **The API key never enters the repo.** `.env` locally, Streamlit Cloud Secrets
  in deployment. `data/index/` *is* committed on purpose; `data/raw/`,
  `data/logs/` and `eval/results/` are ignored on purpose.
- **Streamlit Cloud auto-deploys on push to `main`** — no separate publish step.
  When a change seems not to land, suspect a stale browser page first.
- **The operating threshold `0.82` is a placeholder, not a calibrated value.**
  The report is explicit about the difference. It becomes real only after
  `eval/calibrate.py --apply` runs.

## The open thread

The evaluation chain has never been run end to end, so this milestone has code
but not yet evidence:

```bash
python eval/run_eval.py && python eval/label.py
# caseworker fills eval/results/review_sheet.csv, then:
python eval/label.py --merge && python eval/calibrate.py --apply && python eval/report_results.py
```

## Before you finish a session

If anything changed, add an entry to `PROGRESSION/` and update the index — the
next session relies on it. If the layout changed, run:

```bash
python .claude/skills/pm4-project-context/scripts/refresh_folder_description.py
```
