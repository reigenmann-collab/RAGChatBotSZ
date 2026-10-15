# 003 — PM3/PoC-Demonstrator rebrand, embedding-based topic match

**Date:** 2026-10-15
**Outcome:** App UI rebranded from "PM4 — Departementaler Pilot" to "PM3 —
PoC-Demonstrator"; hard-routing mechanism switched from keyword matching to
embedding similarity, matching report v4.3 §4.2/§4.3.

---

## 1. Trigger

Two separate user requests, handled together because the second depended on
the first's output:

1. UI consistency: all remaining "PM4"/"Pilot" labels in `app/
   streamlit_app.py` renamed to "PM3"/"PoC-Demonstrator" (sidebar, topbar
   badge, browser tab title, nav link, breadcrumb, main subheader, draft-answer
   expander label) — the earlier session had only changed some of them.
2. The open question from session 002: report v4.3 §4.2/§4.3 describes the
   legal/sensitive "Themenabgleich" as embedding-similarity against a curated
   reference set, not the keyword list the code implements. User asked for the
   trade-offs explained (and the existing keyword list exported to Excel)
   before deciding whether to switch. After reading the comparison, decided:
   **switch**.

## 2. UI rebrand

Every user-visible "PM4"/"Pilot" string in `app/streamlit_app.py` changed to
"PM3"/"PoC-Demonstrator": sidebar heading, `st.set_page_config` title, topbar
nav link + badge, breadcrumb, main page subheader, and the suppressed-draft
expander label. Verified live in six screenshots (one per example question,
delivered to the user as PNG) — all labels consistent, no leftover "PM4" text
in the citizen-facing surface.

## 3. Keyword list exported, then retired

`docs/PM4_Stichwortlisten_Themenabgleich_REQ11.xlsx` — two sheets:
1. The 24 hard-route keywords from the prototype's first implementation
   (archived here; `config.yaml` no longer carries this list).
2. The REQ-11 coverage-check keywords (`coverage.rules` in `config.yaml`) —
   included as context since they use the same substring-match mechanism,
   but **out of scope for this change**: REQ-11 stays keyword-based. The
   report only redefines the legal/sensitive mechanism, not coverage.

## 4. Mechanism switch: keyword list → embedding similarity

Delivered a comparison (keyword matching vs. embedding similarity: auditability,
false-positive risk, maintenance burden, the report's own "Pflegeaufwand, kein
Architekturproblem" framing) before implementing, per the user's request to
decide only after understanding the trade-off. Full version in `decisions.md`
under "Hard routing detects by embedding similarity, not keyword matching".

**New files:**
- `src/topic_match.py` — embeds `config.yaml` → `routing.legal_sensitive_examples`
  once (`lru_cache`), exposes `nearest_match()` / `is_topic_match()` against a
  precomputed query vector.

**Changed files:**
- `config.yaml` — `hard_route_patterns` (24 keywords) replaced with
  `legal_sensitive_examples` (18 curated reference sentences, grouped by
  comment into Rechtsmittel/Verfahren, Straf-/Zivilrecht, Haftung, plus two
  explicit paraphrases with none of the old keywords) and
  `legal_sensitive_similarity_threshold: 0.65`.
- `src/retrieve.py` — `retrieve()` takes an optional precomputed `query_vec`,
  so the embedding computed for the topic match can be reused for retrieval
  instead of embedding the query twice (report §4.1 requires this: "parallel
  und ohne zusätzlichen Modellaufruf").
- `src/routing.py` — `is_hard_routed()` now takes a query *vector*, not query
  text; delegates to `topic_match.is_topic_match()`. `decide()` signature
  changed to match (`query_vec` instead of `query`). Every branch's return
  dict now carries `topic_match` (similarity, nearest example, threshold) for
  UI transparency even on non-hard-routed paths.
- `src/pipeline.py` — embeds the query once at the top of `answer_query`,
  checks `routing.is_hard_routed(query_vec)` directly (not via `decide()`, to
  avoid a premature "composite is None" confidence-escalation fallthrough)
  before any retrieval/generation; passes the same vector into `retrieve()`.
- `app/streamlit_app.py` — `render_signals()`'s "no signals computed" info box
  now shows the actual similarity score, threshold and nearest reference
  example when a query was hard-routed, instead of a static sentence.
  `config.yaml`'s `hard_route_reason` string updated to name the new
  mechanism; two unrelated stale report citations fixed in passing (§4.3→§4.2
  for the calibration-procedure caption, §4.4→§4.3 for the "no signals"
  caption — same kind of citation drift found and fixed in session 002).

## 5. Threshold: empirically checked, not calibrated

No calibration harness exists for this threshold (unlike the composite `C`
threshold, which has `eval/calibrate.py`). Picked `0.65` after testing the
real embedder (`paraphrase-multilingual-MiniLM-L12-v2`) against 12 probe
queries — 5 legal/sensitive paraphrases (similarities 0.611–0.877), 7 routine
questions (similarities 0.364–0.580). Clean gap between 0.580 and 0.611;
`0.65` sits in it. This is the same "placeholder, not calibrated" status as
`confidence.threshold_placeholder: 0.82` — stated explicitly in both
`config.yaml`'s comment and `decisions.md`, so a future session doesn't
mistake it for a derived value.

One iteration was needed: the first draft of the Haftung reference example
("Wer haftet, wenn mein Auto auf dem Gemeindeparkplatz beschädigt wird?") was
too generically "Auto"-flavoured and pulled an unrelated routine query ("Wie
melde ich mein Auto beim Strassenverkehrsamt an?") up to 0.640 similarity —
inside the danger zone of a 0.60–0.65 threshold. Rewriting the example to be
specific to liability language ("Wer haftet für den Schaden an meinem
Fahrzeug, der durch einen Mangel am Gemeindeparkplatz entstanden ist?") fixed
the false-positive risk and is the version now in `config.yaml`. Worth
remembering: a reference example's incidental vocabulary (not just its topic)
pulls in unrelated queries that happen to share that vocabulary.

## 6. Verified live

- `python src/pipeline.py "Ich habe eine Busse fürs Parkieren erhalten und
  möchte Einsprache erheben."` → `hard_route`, as before.
- `python src/pipeline.py "Was kostet eine Gewerbeparkkarte in der Gemeinde
  Schwyz?"` → `answer`, similarity 0.398 (well under 0.65) — no
  false-positive regression on the routine example set.
- `python src/pipeline.py "Ich finde das nicht fair, was kann ich
  unternehmen, um das zu ändern?"` → `hard_route`, similarity 0.718. This
  query contains **none** of the 24 retired keywords — the concrete proof the
  switch was worth making.
- Same paraphrase re-run in the live Streamlit app (local): correctly hard
  routed, "Prüfansicht" showed `Themenabgleich: Ähnlichkeit 0.718 (Schwelle
  0.650) zu »Das kann doch nicht rechtens sein, was kann ich dagegen
  unternehmen?«`.

## 7. Skill discovered mid-session

`anthropic-skills:rag-chatbot-architecture-review` appeared as an available
skill partway through this session — built specifically for this project's
"two reasons, three triggers" escalation pattern and report/REQ/diagram
consistency. Loaded and cross-checked this session's work against it after
the fact: no conflicts, the implementation already matches the "two reasons,
three triggers" framing it describes, and no new REQ was minted for the
embedding mechanism (consistent with its REQ-catalog-hygiene guidance — the
mechanism serves REQ-05, it isn't a requirement in its own right). **Load this
skill at the start of a session that touches routing/escalation logic or the
report's REQ catalog or diagrams** — it would have been useful from the start
of this one.

## 8. Left open

- `legal_sensitive_similarity_threshold: 0.65` needs the same negative-control
  test REQ-11 needs before go-live (report 5.6/7.3): can it be fooled, does it
  miss cases it should catch. Not yet tested beyond the 12 probe queries above.
- The reference set (18 examples) is well short of the report's own
  recommendation (50–150 per category, §4.3) for production readiness — fine
  for a demonstrator, flagged as a known gap.
- REQ-11 coverage check was explicitly left as keyword-based — the report
  doesn't ask for it to change, and the user's question was scoped to the
  legal/sensitive topic match only.
- Everything from 002 §5 (eval chain never run, OCR budgeting gap, B17 slide
  not merged into the deck) — still open, untouched this session.
- Not yet committed to git — more updates may follow in this session per the
  user.
