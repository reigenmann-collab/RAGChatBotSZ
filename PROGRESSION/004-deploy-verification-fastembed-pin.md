# 004 — Deploy verification: cross-environment embedding drift found and pinned

**Date:** 2026-10-15
**Outcome:** Found that the new embedding-based topic match (003) behaved
differently on Streamlit Cloud than locally for a borderline query, traced it
to an unpinned `fastembed` version, pinned `fastembed`/`onnxruntime` exactly.
Re-verification after the fix pending the next deploy.

---

## 1. What happened

After pushing 003 (PM3 rebrand + embedding-based topic match) and confirming
Streamlit Cloud had redeployed (tab title updated to "PM3", UI labels correct),
re-ran the two topic-match test queries from 003 §6 live on
https://ragchatbotsz-4gfjul5ikk4khr3wotj9s8.streamlit.app/:

| Query | Local result (003 §6) | Deployed result |
|---|---|---|
| "Ich habe eine Busse fürs Parkieren erhalten und möchte Einsprache erheben." | hard_route | **hard_route** ✓ |
| "Ich finde das nicht fair, was kann ich unternehmen, um das zu ändern?" | hard_route, similarity 0.718 | **escalate_confidence**, composite 0.807 — topic match did not fire at all |

The high-margin case (similarity 0.830 locally) still routed correctly. The
borderline case (0.718 locally, threshold 0.65 — a margin of only 0.068)
flipped: the deployed environment's embedding of the same query text against
the same reference set apparently produced a similarity below 0.65, so no
topic match, so the query fell through to full generation — which then
escalated anyway, but via the confidence trigger, not the topic match. The
citizen-facing outcome (escalated, no automated answer) was the same by
coincidence; the *mechanism* that fired was not, which matters for the
negative-control test planned in 003 §8 and for the architecture claim itself.

## 2. Root cause

`requirements.txt` pinned `fastembed>=0.8` — unbounded above. Local dev
environment has `fastembed==0.8.0` (the floor). Streamlit Cloud resolves
`requirements.txt` fresh on each rebuild and is not guaranteed to land on the
same minor/patch version, especially after any delay between builds. A
version difference in `fastembed` (which bundles the ONNX inference path for
`qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`) is enough to shift
embeddings measurably — this is not hypothetical on this exact model: the
code's own pre-existing warning (`src/retrieve.py`, surfaced at runtime) notes
that a past `fastembed` version change switched this model from CLS-token to
mean-pooling embeddings, i.e. a real precedent for this model's embedding
output changing between library versions.

This is the same instability class already documented in `decisions.md` for
the Jina embedding NaN-vector bug (001) — different onnxruntime/Python
combinations behaving differently — just surfacing again through an
unpinned transitive version instead of a model swap.

## 3. Fix applied

`requirements.txt`: `fastembed==0.8.0` and `onnxruntime==1.29.0`, pinned
exactly to match local dev (previously `fastembed>=0.8`; `onnxruntime` was an
unpinned transitive dependency, not listed at all). Comment added explaining
why, cross-referencing this entry and the `legal_sensitive_similarity_threshold`
decision.

**This likely narrows the problem but may not fully close it.** The ONNX
model used is a quantised ("-Q") build; quantised-kernel numerics can still
differ slightly across CPU microarchitectures (Streamlit Cloud's Linux
container vs. local Windows dev) even with byte-identical library versions.
Pinning removes the *version-drift* axis, not necessarily every *platform*
axis. This is a second, independent reason (beyond the "Pflegeaufwand"
argument already in `decisions.md`) why the 0.65 threshold's margin matters:
a borderline case within ~0.07 of the threshold is exactly the kind of case
this instability can flip, which is one more argument for treating 0.65 as
unvalidated until the negative-control test (003 §8) explicitly includes a
cross-environment check, not just cross-phrasing.

## 4. Status

Fix pushed; Streamlit Cloud rebuild triggered. **Not yet re-verified** — the
borderline query needs to be re-run against the live deployment once the
rebuild completes to confirm the pin actually closes the gap. If it doesn't,
the next step is either widening the threshold's safety margin or accepting
that quantised ONNX models need a tolerance band rather than a hard cosine
cutoff.

## 5. Left open

- Re-verify the borderline query on the deployed app after this rebuild.
- Everything from 003 §8 unchanged (reference set still only 18 examples,
  negative-control test not run) — now explicitly scoped to include a
  cross-environment check.
- Everything from 002 §5 (eval chain, OCR budgeting gap, B17 slide) — still
  open, untouched.
