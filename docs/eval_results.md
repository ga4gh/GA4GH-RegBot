# Retrieval Evaluation Results — GSoC 2026 Phase 2

Metric definitions and procedure: [`DESIGN.md` §4.2](DESIGN.md). Harness:
[`src/regbot/evaluation.py`](../src/regbot/evaluation.py). Gold set:
[`examples/eval/gold_ga4gh.yaml`](../examples/eval/gold_ga4gh.yaml).

Reproduce:

```bash
python -m src.main ingest-manifest --reset
python -m src.main benchmark --gold examples/eval/gold_ga4gh.yaml --label baseline
```

> **Status:** the gold set was drafted by the contributor and is **not yet mentor-reviewed**.
> Numbers below are a working baseline for the Phase 2 discussion, not a validated benchmark.

---

## 1. Setup

| | |
|---|---|
| Corpus | 128 chunks / 22 documents (P0 GA4GH, P1 GDPR briefs, P2 six East Asia jurisdictions) |
| Gold set | v0.2 — 12 queries, 41 resolved gold chunks, 0 skipped |
| Embeddings | `all-MiniLM-L6-v2`, cosine |
| Fusion | Reciprocal rank fusion over dense + BM25 |
| Date | 2026-07-27 |

The §2 sweep was run on the earlier 13-document corpus (91 chunks); §3 onward reports the
full 22-document corpus. §4 documents what changed between them, which turned out to be the
most informative result in this phase.

**Why anchors instead of chunk ids.** Chunk ids embed a SHA-256 of the *absolute ingest
path* (`ingestion._stable_source_id`), so an id recorded on one machine never resolves on
another. Gold labels are therefore `(document_id, contains)` anchors resolved against the
live manifest at benchmark time. Anchors that match nothing are reported as
`unresolved_anchors`, and a query whose anchors all fail is **skipped, not scored** — a
stale gold set fails loudly instead of silently inflating recall.

**Precision denominator.** `precision@k` divides by the number of results actually
returned, not by `k`. On a 91-chunk corpus with a jurisdiction filter active, retrieval
legitimately returns fewer than `k` candidates (e.g. 3 for `TW`), and dividing by `k` would
score that as a precision failure. Each row records `returned` so the denominator is
auditable.

---

## 2. Candidate-pool sweep

Both pools feed RRF; the sweep varies how many candidates each retriever contributes.

| Config | R@1 | R@3 | R@5 | **R@8** | MRR@8 | P@8 |
|--------|-----|-----|-----|---------|-------|-----|
| baseline `sem=24 bm25=24` | 0.419 | 0.686 | 0.807 | 0.844 | 0.944 | 0.427 |
| `sem=48 bm25=48` | 0.419 | 0.686 | 0.807 | 0.865 | 0.944 | 0.424 |
| `sem=91 bm25=91` (full corpus) | 0.419 | 0.686 | 0.807 | 0.865 | 0.944 | 0.410 |
| `sem=48 bm25=12` (dense-weighted) | 0.419 | 0.728 | 0.765 | 0.824 | **0.958** | 0.417 |
| **`sem=12 bm25=48` (lexical-weighted)** | 0.419 | 0.707 | 0.807 | **0.886** | 0.938 | **0.434** |

**Adopted: `sem=12, bm25=48`** — best recall@8 *and* best precision@8, i.e. not a
recall-for-precision trade. This matches the DESIGN §2.3 rationale for keeping BM25 in the
loop: statutory text turns on rare exact terms ("pseudonymisation", "Recital 33",
"Section 33"), which lexical matching handles better than a 384-dim general-purpose
embedding.

Dense-weighting (`sem=48 bm25=12`) wins MRR@8 (0.958 vs 0.938) — it places its first
correct hit slightly higher — but loses 6 points of recall. Recall is the primary metric
per DESIGN §4.2, since a reviewer reads the whole top-k list.

Defaults now live in [`config.py`](../src/regbot/config.py), overridable via
`REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES`.

### Depth sweep (at full pools)

| k | Recall@k | Precision@k | MRR@k |
|---|----------|-------------|-------|
| 8 | 0.865 | 0.410 | 0.944 |
| 12 | 0.886 | 0.361 | 0.944 |
| 16 | 0.886 | 0.332 | 0.944 |
| 20 | 0.886 | 0.314 | 0.944 |

Recall saturates at k=12 while precision decays monotonically. **`top_k=8` stays the
default**: going deeper buys ~2 points of recall at a 12-point precision cost, and every
extra chunk is more text a DPO/IRB reviewer has to read.

---

## 3. Adopted configuration

`sem=12, bm25=48, top_k=8`, exact dense ranking, on the full 22-document corpus, gold v0.2.

**recall@8 = 0.876, precision@8 = 0.490, MRR@8 = 0.840, recall@5 = 0.723.**

Reproducible bit-for-bit: three consecutive runs of `python -m src.main benchmark` return
identical figures. That was not true before §5.

### Reading the results

**Jurisdiction-filtered queries score 1.00 across the board.** The filter cuts the
candidate space to 3–4 chunks, so retrieval is nearly trivial once scoping works. This
validates the Phase 1 jurisdiction metadata, but these six queries should **not** be read
as evidence of retrieval quality — they mostly measure that the filter works. The
unfiltered queries are the real test.

**Remaining weaknesses**, both unfiltered and sharing one root cause:

- **q11-reidentification (R@8 = 0.50, MRR = 0.25)** — the worst result. The query
  ("attempt re-identification of anonymized data") is semantically close to a large block
  of generic privacy/security prose, which crowds out the specific FRS prohibition
  ("Forego any attempt to re-identify anonymized data") down to rank 6.
- **q10-broad-consent-validity (R@8 = 0.43)** — gold spans 7 chunks across the broad-consent
  brief and its legal-basis counterpart; the top-8 saturates on the first document.

Both are **multi-chunk topic coverage** failures: gold spread across several overlapping
chunks, where the top-8 locks onto one facet. MRR stays high (0.840) because the *first*
hit is usually correct — the system is good at finding *a* relevant clause and weaker at
finding *all* of them. For output that feeds a DPO/IRB checklist, complete topic coverage
matters more than the top hit, so this is the priority for further work.

---

## 3b. Two ranking heuristics, measured and rejected

An earlier draft of this document recommended **per-document diversification** (cap chunks
per document in the fused list) as the targeted fix for the multi-chunk gap. Inspecting the
actual rankings **refuted that recommendation before it was implemented**, and the
correction is worth recording.

For q10, the top three results are already all from the correct gold document, and the
fourth gold chunk *of that same document* sits at rank 13. Capping per document would push
it further down. The retriever was not under-diversifying — if anything the opposite.

Both the rejected idea and its inverse were then measured against the deterministic
baseline:

| Config | R@3 | R@5 | R@8 | MRR@8 | P@8 |
|--------|-----|-----|-----|-------|-----|
| **exact RRF (adopted)** | 0.689 | 0.723 | **0.876** | 0.840 | 0.490 |
| sibling boost α=0.05 | 0.716 | 0.779 | 0.848 | 0.861 | 0.479 |
| sibling boost α=0.10 | 0.689 | **0.834** | 0.848 | **0.861** | 0.479 |
| sibling boost α=0.25 | 0.702 | 0.779 | 0.820 | 0.850 | 0.458 |
| diversify cap=2/doc | 0.510 | 0.531 | 0.683 | 0.840 | 0.490 |
| diversify cap=3/doc | 0.689 | 0.723 | 0.876 | 0.840 | 0.524 |

"Sibling boost" adds `α ×` the summed RRF score of a chunk's parent document, on the theory
that if several chunks of a document rank highly, its other chunks are likely relevant too.

**Neither was adopted:**

- **Diversification is harmful.** `cap=2` costs 19 points of recall@8 (0.876 → 0.683).
  `cap=3` and `cap=4` are recall-neutral. The original recommendation was wrong.
- **`cap=3`'s precision gain (0.490 → 0.524) is largely an artefact of our own metric.**
  Capping can return fewer than 8 results, and precision@k divides by results returned
  (§1). Finding the same gold in a shorter list mechanically raises precision. That is not
  a real quality improvement.
- **Sibling boost is a trade, not a win.** α=0.10 buys 11 points of recall@5 and 2 points of
  MRR, and pays 2.8 points of recall@8. Defensible if you optimise for what a reviewer sees
  first — but it is a genuine trade-off, not a free gain.

With 12 self-labelled queries, a 2–3 point difference is roughly one chunk moving in one
query. Tuning a ranking heuristic against that would be fitting noise. The measured gain
this phase came from **fixing non-determinism** (§5) — a principled correctness fix — not
from a ranking heuristic. Sibling boost is worth revisiting once the gold set is
mentor-reviewed and larger; the experiment script is reproducible from this table.

---

## 4. What corpus growth did to the numbers

Mid-phase the corpus went from 13 to 22 documents (the nine entries that were listed in
`corpus_manifest.yaml` but had never been ingested). Re-running the same harness produced
the single most useful result of this phase:

| Run | Corpus | Gold | R@8 | MRR@8 | P@8 |
|-----|--------|------|-----|-------|-----|
| A | 13 docs / 91 chunks | v0.1 | 0.886 | 0.938 | 0.434 |
| B | 22 docs / 128 chunks | v0.1 (stale) | 0.828 | 0.778 | 0.417 |
| C | 22 docs / 128 chunks | v0.2 (relabelled) | 0.855 | 0.840 | 0.479 |

**A → B: recall appeared to drop 6 points.** Inspecting the actual rankings showed most of
that was *not* a retrieval regression. The newly ingested documents include briefs written
specifically on existing query topics — `gdpr-international-transfers` for q03,
`gdpr-withdrawal-consent` for q01 — which retrieval correctly ranked first and the stale
gold set scored as misses. Two of the three apparent regressions were labelling artefacts.

**B → C: relabelling recovered recall to 0.855 and raised precision to 0.479** (its best
value in any run — correct retrievals stopped being counted as noise).

**C is still below A, and that gap is real.** More documents on overlapping topics means
more genuine competitors per query. The 0.886 from run A was partly an artefact of a corpus
too small to contain distractors. Run C is the honest number.

The operational lesson, which matters more than any single score: **a gold set is only
valid against the corpus it was written for.** Growing the corpus silently invalidated it,
and the failure mode was a metric that looked like a code regression. `benchmark` should be
re-run and the gold set re-reviewed on every corpus change — worth encoding as a checklist
item before the CI gate is switched on.

---

## 5. The benchmark was not reproducible (and the fix)

Running `python -m src.main benchmark` three times with no changes produced **three
different scores**:

```
R@5=0.7024  R@8=0.8552  MRR@8=0.8333
R@5=0.7093  R@8=0.8413  MRR@8=0.8361
R@5=0.7024  R@8=0.8552  MRR@8=0.8333
```

A ±1.4-point swing in recall@8 makes the §2 sweep hard to trust — the winning
configuration there beat the baseline by 4.2 points, only about three times the noise — and
it makes `--min-recall` unusable as a CI gate, since a gate that fails at random is worse
than none.

**Diagnosis.** Narrowed by elimination:

| Suspect | Result |
|---------|--------|
| Embedding model output | Stable — identical SHA across processes |
| BM25 scoring | Stable |
| Chroma dense query *within* one process | Stable across 5 repeats |
| Chroma dense query *across* processes | **Unstable** |

Only one of twelve queries (q09) was affected, and only at rank 8 — ranks 1–7 were
identical. The culprit was pool membership, not ordering: Chroma's **HNSW index is
approximate**, and the same query embedding returned different *tail* neighbours across
process starts. One chunk drifting in or out at position 12 of the dense pool changed the
fused top-8.

**Fix.** Two changes:

1. **Exact cosine ranking.** `HybridRetriever` loads all stored embeddings once and ranks
   by exact dot product instead of querying the ANN index. This costs nothing
   architecturally — the retriever already holds every chunk's full text in memory for
   BM25, so memory was already proportional to corpus size. At 128 chunks × 384 dims it is
   a few hundred kilobytes. Chroma remains the persistence layer. If embeddings cannot be
   loaded, the code falls back to the ANN query rather than failing.
2. **Deterministic tie-breaks.** Both dense ranking and RRF now sort by `(-score, chunk_id)`.
   Without it, equal scores order by dict insertion, so the ranking depended on upstream
   pool order rather than on relevance.

**Result — determinism and a genuine quality gain:**

| | R@5 | R@8 | MRR@8 | P@8 | Reproducible |
|---|-----|-----|-------|-----|--------------|
| ANN (before) | 0.702–0.709 | 0.841–0.855 | 0.833–0.836 | 0.479 | ❌ |
| Exact (after) | 0.723 | **0.876** | 0.840 | **0.490** | ✅ |

Recall@8 improved by ~2–3.5 points *because the approximate index had been silently
dropping true nearest neighbours*. The accuracy gain was a side effect; reproducibility was
the goal.

Pinned by `tests/test_retrieval.py`, which stubs the embedding matrix so CI needs no model
download.

**All §2 numbers predate this fix** and carry roughly ±1.4 points of noise. The §2 ranking
of configurations is probably still right — the lexical-weighted config won on both metrics
and by more than the noise band — but it should be re-run before being quoted as settled.

---

## 6. Threats to validity

Stated plainly, because the numbers look better than the evidence supports:

1. **The gold set is self-labelled.** Written by the same contributor who tuned the
   retriever. Needs mentor review before it means anything externally.
2. **12 queries on 91 chunks.** A 4-point recall difference is roughly one chunk moving in
   one query. The adopted config is a reasonable default, not a settled result.
3. **20 of 22 documents are contributor-authored summaries, not primary law.** Only
   `ga4gh-frs` and `ga4gh-consent-policy` are source PDFs; the rest are ~300–450-word
   paraphrases (their file headers say so, and chunks now carry
   `content_type: primary|summary` so this is queryable). Retrieval scored against a
   paraphrase does not demonstrate retrieval against statutory text, and the phrasing of
   both the summaries and the queries came from the same author — a vocabulary-overlap
   bias that inflates BM25 in particular. **This is the largest threat on the list.**
4. **Anchors resolve more broadly than intended.** With 150-char chunk overlap, a phrase
   like `Recital 33` matches adjacent chunks, so some queries have larger gold sets than
   hand-specified (q10: 7 chunks from 3 anchors). This deflates recall slightly — a
   conservative bias, but not a deliberate one.
5. **No re-ranker was tested.** The proposal listed it as conditional ("if beneficial").
   Given the failure mode is recall spread across chunks rather than mis-ranking, a
   cross-encoder would likely not fix q10/q11 — it reorders a candidate list that is
   already missing the gold chunks.
6. **The §2 sweep predates the determinism fix** (§5) and carries ±1.4 points of noise.
   Its conclusions are probably safe but are not settled until re-run.

## 7. Next steps

- [ ] Mentor review of the gold set — the blocking item.
- [ ] Re-run the §2 candidate-pool sweep on the now-deterministic retriever.
- [ ] Expand to ~30 queries, weighted toward unfiltered multi-chunk topics.
- [ ] Revisit sibling boost (§3b) once the gold set is larger and reviewed — it looks
      promising for recall@5 but is not separable from noise at n=12.
- [ ] Replace contributor summaries with primary statutory text where licensing permits;
      re-run and expect recall to *drop*. Treat that as the honest baseline. Use
      `content_type` to measure the primary-vs-summary split explicitly.
- [ ] Re-run `benchmark` and re-review the gold set on **every** corpus change (see §4).
- [ ] Wire `benchmark --min-recall` into CI as a regression gate once the gold set is
      approved. Now viable: the benchmark is reproducible (§5), so the gate will not flake.
      Currently passes at 0.85.
- [ ] Reconsider `precision@k`'s denominator. Dividing by results returned (§1) is right
      for jurisdiction-filtered queries but rewards configurations that return fewer
      results, as §3b showed. Reporting `returned` alongside is a partial mitigation;
      reporting both denominators would be better.
