# PM4 — Scope decisions and corpus findings

Companion note to the prototype. It records what was decided, what the real
source data turned out to be, and where the prototype departs from the written
project report. Everything here is a finding to be reported at the PM4 gate, not
a defect to be quietly fixed.

---

## 1. Scope as fixed by the report

Report 5.2 scopes the pilot to **parking-permit inquiries only, from the Traffic
Department**, with the corpus limited to *"the current parking ordinance, its
addenda and the related forms."* PM4 (Table 16) is the Departmental Pilot,
target 29 July 2026, sitting between the proof of concept and PM5 production
rollout.

That scope was kept. The prototype covers municipal road traffic and parking for
Gemeinde Schwyz and nothing else.

---

## 2. Finding: the corpus the report assumes does not exist

The Gemeinde Schwyz Erlasssammlung contains 68 ordinances. **None of them is a
parking ordinance.** The only parking-specific Erlass is *1.45 Verordnung über
Personalparkplätze* — staff parking for municipal employees, an internal matter,
not a citizen-facing one.

Two consequences follow, and both matter for the report's narrative.

### 2.1 The municipality issues no resident parking permits

The Parkplätze page states plainly that Gemeinde Schwyz issues no parking cards
at all, with the sole exception of Gewerbeparkkarten for tradespeople. Long-term
parking is rented commercially at Parkhaus Hofmatt or Parkhaus MythenForum.

Report 3.3 uses as its decisive example *"a citizen asking whether they qualify
for a second residential permit."* That inquiry has **no factual basis** in the
real municipality. The example should be replaced in the report with one the
corpus can actually support — the Gewerbeparkkarte eligibility rules serve the
same rhetorical purpose and are real.

### 2.2 The fee schedule is a web page, not an ordinance

Parking tariffs — ten car parks, each with its own rate, maximum duration and
chargeable hours — live only on the Parkplätze content page. No ordinance
contains them.

This reproduces the PoC's own failure mode (report 5.6) in the live source data:
authoritative fee information sitting outside the document set a retrieval
system would naturally index. The prototype therefore assigns that page
`doc_type: gebuehrentarif` so the REQ-11 coverage check can require it. This is
not a workaround — it is the corpus-governance decision report 2.4 says has to be
made explicitly and by a named owner.

**Verified in practice:** the query *"Was kostet eine Gewerbeparkkarte?"*
retrieves only `verordnung` chunks and fails the coverage check, escalating even
at a composite score of 0.9. REQ-11 fires on real data, unstaged.

---

## 3. Finding: four of five road-traffic Erlasse are unreadable scans

| Erlass | Pages | Text layer |
|---|---|---|
| 1.45 Verordnung über Personalparkplätze | — | native text |
| 4.20 Verordnung über Strassenbeiträge | 2 | **image only** |
| 4.21 Plan zur Strassenbeitragsverordnung | 2 | **image only** |
| 4.25 Einführung der Vorteilsabgabe (§ 58 StrVO) | 1 | **image only** |
| 4.75 Verordnung über den öffentlichen Verkehr | 2 | **image only** |

Without a text layer these documents cannot be retrieved. In the terms of report
7.6: *a document that is not indexed does not exist.* The prototype adds an
explicit OCR step (`src/ocr.py`) that transcribes each scanned page with a vision
model and caches the result.

This is a genuine operational finding for the roadmap. Report 7.4 Phase 1 budgets
for indexing a fee-schedule addendum; it does not budget for OCR of the ordinance
back-catalogue, and the Content Governance Group's monthly refresh (report 7.5)
has no defined procedure for a scanned document. **Recommend adding both to the
Gate 1 checklist.**

---

## 4. Corpus as actually indexed

| Document | Type | Indexed |
|---|---|---|
| Parkplätze (tariffs, 10 car parks) | `gebuehrentarif` | yes |
| Gewerbeparkkarten (service page) | `dienstleistung` | yes |
| Gewerbeparkkarten-Konzept Merkblatt | `merkblatt` | yes |
| 1.45 Verordnung über Personalparkplätze | `verordnung` | yes |
| 4.20 / 4.25 / 4.75 Erlasse | `verordnung`, `gebuehrentarif` | after OCR |
| Gewerbeparkkarten Übersichtsplan | `plan` | **no** |
| 4.21 Plan zur Strassenbeitragsverordnung | `plan` | **no** |

The two plans are excluded deliberately. The Übersichtsplan does carry a text
layer, but it is 58,000 characters of cadastral parcel numbers and street labels
with no answerable content. Indexing it would add spurious high-similarity
matches and inflate S1 on queries it cannot actually answer. Both remain in the
manifest as documented ingestion gaps.

---

## 5. Statistical consequence for the PM4 gate

Report 5.3 requires the test set to reach **at least 150 parking-domain queries**
before production go-live, bringing the rule-of-three upper bound on the
safe-failure rate to roughly 2%.

The indexed corpus does not contain 150 distinct answerable questions. The test
set here is **50 queries** (32 realistic, 18 synthetic), giving a 95% upper bound
of **6.0%** even if zero safe-failures are observed.

**This should be reported at the gate as not met.** Report 7.4 Gate 1 makes
expanding the test set to 150 a Phase 1 condition; on the evidence, expanding the
*corpus* is a prerequisite for expanding the *test set*, and that dependency is
not currently in the plan.

---

## 6. Deviations from the report's requirements

| Requirement | Status in prototype | Note |
|---|---|---|
| REQ-01 answer from verified documents | met | German, citations mandatory |
| REQ-02 escalate below threshold | met | `src/routing.py` |
| REQ-03 auto-summary on escalation | met | degrades safely on failure |
| REQ-05 hard-route legal matters | met | evaluated *before* generation |
| REQ-06 < 5 s response | measured | single-user only; no concurrent-load test |
| **REQ-07 Swiss infrastructure** | **not met** | retrieval and embeddings are local; generation calls an external API |
| REQ-08 pseudonymised logs | met | salted SHA-256, raw query never written |
| REQ-09 audit escalations | met | `data/logs/audit.jsonl` |
| REQ-11 coverage check | met | independent trigger, fires on real data |

REQ-07 is the deviation that matters. It was an explicit project decision to use
an external API for the prototype rather than stand up a local model. A
production pilot cannot ship this way, and report 6.4 makes the DPO a gate
blocker precisely on this point.

---

## 7. Technical notes

- **Embedding model.** `jinaai/jina-embeddings-v2-base-de` was the first choice
  as a German-native model, but its ONNX build emits NaN vectors under
  onnxruntime 1.29 on Python 3.14. Replaced with
  `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384d), verified
  working. Retrieval quality is correspondingly weaker and is a known limitation.
- **Chunk embedding.** Chunks are embedded with the document title prefixed;
  without it, mid-document chunks lose all trace of their source document and
  recall drops on queries that name the document.
- **HTML extraction.** The i-web CMS renders login, search and breadcrumb chrome
  inside the content column — roughly 2,600 identical characters per page.
  Stripping it was necessary: left in, it pulls unrelated chunks toward each
  other and dilutes retrieval.
- **Incomplete counts as failure.** In calibration, an `incomplete` label is a
  failure, not a partial success. Treating it otherwise would calibrate the
  threshold against the very failure mode REQ-11 exists to catch.
