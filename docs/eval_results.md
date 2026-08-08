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
| Corpus | 864 chunks / 23 documents — 16 primary / 7 summary (see §4b, §4c, §4h) |
| Gold set | v0.4 — 12 queries, 0 skipped |
| Embeddings | `all-MiniLM-L6-v2`, cosine |
| Fusion | Reciprocal rank fusion over dense + BM25 |
| Date | 2026-07-28 |

**Headline: provision-level recall@8 = 0.846, chunk-level 0.713, over a primary-source corpus (§4b–§4d).** Sections 2, 3 and 3b
report the earlier paraphrase corpus, which scored higher for reasons §4b explains; they are
kept because the tuning conclusions drawn there still hold. §4 and §4b document what changed
and why the number fell.

**Why anchors instead of chunk ids.** Chunk ids embed a SHA-256 of the *absolute ingest
path* (`ingestion._stable_source_id`), so an id recorded on one machine never resolves on
another. Gold labels are therefore `(document_id, contains)` anchors resolved against the
live manifest at benchmark time. Anchors that match nothing are reported as
`unresolved_anchors`, and a query whose anchors all fail is **skipped, not scored** — a
stale gold set fails loudly instead of silently inflating recall.

**Precision denominator.** `precision@k` divides by the number of results actually
returned, not by `k`. With a jurisdiction filter active, retrieval legitimately returns
fewer than `k` candidates (e.g. 3 for `TW`), and dividing by `k` would score that as a
precision failure. Each row records `returned` so the denominator is auditable. This choice
has a downside of its own — see §3b.

---

## 2. Candidate-pool sweep

Both pools feed RRF; the sweep varies how many candidates each retriever contributes.

Re-run on the deterministic retriever (§5), 22-document corpus, gold v0.2. Every figure
below is reproducible.

| Config | R@1 | R@3 | R@5 | **R@8** | MRR@8 | P@8 |
|--------|-----|-----|-----|---------|-------|-----|
| `sem=24 bm25=24` (original default) | 0.366 | 0.689 | 0.702 | 0.806 | 0.872 | 0.448 |
| `sem=48 bm25=48` | 0.366 | 0.647 | 0.723 | 0.806 | 0.882 | 0.448 |
| `sem=128 bm25=128` (full corpus) | 0.366 | 0.647 | 0.723 | 0.806 | 0.882 | 0.420 |
| `sem=48 bm25=12` (dense-weighted) | 0.366 | 0.709 | 0.723 | 0.786 | **0.889** | 0.438 |
| `sem=24 bm25=64` | 0.366 | 0.647 | 0.702 | 0.820 | 0.872 | 0.445 |
| `sem=8 bm25=64` | 0.324 | 0.689 | **0.737** | 0.855 | 0.840 | 0.465 |
| `sem=12 bm25=96` | 0.324 | 0.689 | 0.723 | 0.834 | 0.840 | 0.441 |
| **`sem=12 bm25=48` (adopted)** | 0.324 | 0.689 | 0.723 | **0.876** | 0.840 | **0.490** |

**Adopted: `sem=12, bm25=48`** — best recall@8 (by 2.1 points over the next config) and
best precision@8. It beats the original 24/24 default by **7 points of recall@8**. This
matches the DESIGN §2.3 rationale for keeping BM25 in the loop: statutory text turns on
rare exact terms ("pseudonymisation", "Recital 33", "Section 33"), which lexical matching
handles better than a 384-dim general-purpose embedding.

**There is a real trade-off, which measurement noise had previously hidden.** Every
lexical-weighted config scores *lower* on R@1 (0.324 vs 0.366) and MRR@8 (0.840 vs
0.872–0.889) than the dense-weighted ones. Dense retrieval is better at putting *one* good
chunk first; lexical weighting is better at finding *more* of them. `sem=48 bm25=12` has
the best MRR in the table and the worst recall@8.

The choice follows from what the output is for: RegBot's report feeds a DPO/IRB/DAC
checklist, where a reviewer reads the whole top-k list and a missed clause is the costly
error. Recall is the primary metric per DESIGN §4.2. A product optimised for a
single-answer chat response would reasonably choose the opposite.

Defaults live in [`config.py`](../src/regbot/config.py), overridable via
`REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES`.

### Depth sweep

| k | Recall@k | Precision@k | MRR@k |
|---|----------|-------------|-------|
| 8 | 0.876 | 0.490 | 0.840 |
| 12 | 0.886 | 0.361 | 0.840 |
| 16 | 0.886 | 0.332 | 0.840 |
| 20 | 0.886 | 0.314 | 0.840 |

Recall saturates at k=12 while precision decays monotonically. **`top_k=8` stays the
default**: going deeper buys ~1 point of recall at a 13-point precision cost, and every
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

## 4b. Moving to primary sources — the honest baseline

§6.3 listed "20 of 22 documents are contributor summaries" as the largest threat to
validity, and §7 predicted that replacing them would make recall **drop**. Both have now
been done and measured.

**What changed.** P0/P1 moved from contributor paraphrases to primary sources:

| | Before | After |
|---|--------|-------|
| Documents | 22 (2 primary / 20 summary) | 22 (14 primary / 8 summary) |
| Chunks | 128 | **689** |
| Primary-source chunks | ~48 (37%) | **658 (96%)** |
| Chunks with `section` | 42% | **78%** |

Sources: the consolidated GDPR text from the EU Publications Office (CELEX 32016R0679 —
all 99 Articles and the recitals, ~54,900 words), the GA4GH Privacy and Security Policy as
published (18pp), and the GA4GH Regulatory & Ethics Toolkit, DUO, MRCG and GDPR Brief pages
as published. `gdpr-legal-basis-without-consent` was dropped: the full GDPR text supersedes
that paraphrase (Articles 6, 9(2)(j), 89). P2 regional law remains contributor summaries by
design and is marked `content_type: summary`, surfaced as a red badge in both UIs.

**The gold set broke, loudly.** Every P0/P1 anchor pointed at paraphrase wording that no
longer exists. The harness skipped 2 queries outright and silently shrank the gold set of
several others — exactly the failure mode §4 was written about, and exactly why an
unresolvable anchor is reported rather than scored as a miss. Gold v0.3 re-anchors those
queries onto **operative provisions in the law itself** — Art. 7(3) for withdrawal, Art. 35
for DPIA, Art. 44/46 for transfers, Recital 33 for broad consent — so a relevance judgment
is now a judgment about the regulation rather than about the contributor's own wording.

**Result:**

| Corpus | Gold | R@1 | R@3 | R@5 | **R@8** | MRR@8 | P@8 |
|--------|------|-----|-----|-----|---------|-------|-----|
| paraphrases, 128 chunks | v0.2 | 0.324 | 0.689 | 0.723 | **0.876** | 0.840 | 0.490 |
| **primary, 689 chunks** | **v0.3** | 0.299 | 0.622 | 0.643 | **0.684** | 0.778 | 0.375 |

**Recall@8 fell 19 points.** That is the headline result of this phase, and it is the
number to trust. Three things drove it, and only one is a retrieval weakness:

1. **The vocabulary-overlap bias is gone.** Queries and paraphrases previously shared an
   author, so BM25 had an unearned edge — the effect §6.3 warned about. Real statutory
   language does not phrase things the way a query does: GDPR Art. 7(3) says "withdraw his
   or her consent at any time", never "withdrawal of consent in genomic data sharing".
2. **The corpus grew 5.4×**, so every query now has far more genuine competitors.
3. **GDPR is 68% of the corpus** (470 of 689 chunks) and floods unfiltered queries.
   q11-reidentification fell to 0.00: the GA4GH re-identification clauses are still there,
   but they no longer surface above 470 chunks of EU regulation.

The earlier 0.876 was substantially an artefact of a small corpus written in the same voice
as the queries. **0.684 over real law is the number the project should be judged on**, and
the one to improve against.

The most promising lever is now clear from cause 3: unfiltered queries over a
GDPR-dominated corpus. `framework` and `jurisdiction` metadata already exist on every
chunk — scoping a GA4GH-framework query away from 470 GDPR chunks is a filter change, not a
ranking change. That is the next experiment.

---

## 4c. Three targeted improvements, measured in sequence

§4b named unfiltered queries over a GDPR-dominated corpus as the next lever. Three changes
followed, each measured on its own so the attribution is clean.

| Step | R@1 | R@3 | R@5 | R@8 | MRR@8 | P@8 |
|------|-----|-----|-----|-----|-------|-----|
| primary corpus, sliding window, additive RRF | 0.299 | 0.622 | 0.643 | 0.684 | 0.778 | 0.375 |
| ① pre-filtering + max fusion | 0.299 | 0.601 | **0.684** | **0.726** | 0.785 | 0.368 |
| ② + section-aligned chunking | **0.533** | 0.635 | **0.709** | **0.733** | 0.785 | 0.231 |
| ③ + Taiwan official law | 0.449 | 0.552 | 0.626 | 0.638 | 0.701 | 0.200 |

### ① Filters now scope retrieval instead of truncating results

A latent bug: filters were applied *after* the top-N candidate cut, so a scoped query did
not search a smaller corpus — it searched the whole corpus and then deleted the results that
did not match. `_allowed_ids` now restricts the candidate universe first.

**The hypothesis this was meant to test was wrong.** §4b predicted q11-reidentification
failed because 470 GDPR chunks drowned it. Scoping to `framework=GA4GH` changed nothing —
still 0 of 4. Inspection showed the real cause: within GA4GH, six of the top eight came from
the 63-chunk Privacy and Security Policy, general privacy prose out-competing the FRS's one
specific prohibition. Enlarging the dense pool did not help either (the sweep is flat from
12/48 to 128/128).

The actual cause was **additive RRF**. The FRS prohibition ranked BM25 **#2** and dense
**#50**; chunks that were merely respectable in *both* channels out-scored it, because
summing rewards corroboration. Switching to `max` fusion — take the best single channel —
gained 4 points of recall@8 and 4 of recall@5. It costs rank-1 accuracy and MRR, the same
trade direction as the lexical-weighted pools and for the same reason. `REGBOT_FUSION=sum`
restores classic RRF.

### ② Section-aligned chunking

Chunks now break at heading boundaries, splitting only inside sections that exceed the size
cap. Straddling chunks fell from 146 of 689 to **15 of 763**, so a citation points at one
article instead of two unrelated obligations.

**Recall@1 jumped 0.299 → 0.533**, but read the precision column with care: P@8 fell to
0.231 largely as an artefact. The gold set is defined by *which chunks contain an anchor
phrase*, so re-chunking changes the gold set itself — several queries went from 2 gold
chunks to 1, which mechanically caps precision@8 at 1/8. **Recall figures are not strictly
comparable across chunking schemes.** The durable justification for this change is the
citation quality, not the metric.

### ③ Taiwan on official law — and why the other five are still summaries

Only Taiwan could be migrated. Of the six P2 jurisdictions:

| | Result |
|---|---|
| **TW** | ✅ MOJ official English text, both Acts, 198 articles, 207 chunks |
| SG, JP | ❌ the sites return a **table of contents only** — the Singapore file had zero occurrences of "shall not", the Japanese one had 109 collapsed-section markers. Ingesting a table of contents would pollute retrieval with structural headings that match query vocabulary and contain no rules, so both were discarded |
| HK, KR | ❌ single-page apps; the served HTML is a 7.5 KB shell |
| CN | ❌ no canonical official English text |

**q02 fell from 1.00 to 0.00**, and that is the most informative number in the table. §3
warned that the P2 queries scoring 1.00 were measuring the jurisdiction filter rather than
retrieval quality. With Taiwan on 3 summary chunks, any retrieval found the answer. With 207
chunks of real statute, the operative withdrawal provision (Human Biobank Management Act
Art. 8) sits at **rank 14** — just outside the top-8, behind genuine but less relevant
biobank provisions. The aggregate drop in step ③ is almost entirely this one query, and it
is a real measurement replacing a hollow one.

---

## 4d. Provision-level recall

§4c showed chunk-level recall is unstable under re-chunking: the gold set is defined by
*which chunks contain an anchor phrase*, so changing the chunker changes the gold set and
the numbers stop being comparable. It also asks the wrong question. A reviewer does not care
whether fragment 3 of Article 35 was retrieved; they care whether **Article 35 was found**.

`provision_keys` identifies a chunk by `document_id § section`, falling back to page and
then to the document. `provision_recall@k` is the fraction of gold *provisions* covered by
the top-k, regardless of which fragment surfaced. Pinned by `tests/test_evaluation.py`,
including the defining property: splitting one provision across more chunks must not change
the score.

| Metric | @1 | @3 | @5 | @8 |
|--------|----|----|----|----|
| chunk-level recall | 0.468 | 0.565 | 0.607 | 0.628 |
| **provision-level recall** | 0.569 | 0.639 | 0.660 | **0.729** |

Provision recall is 8 points higher because retrieval often surfaces *a* fragment of the
right rule while missing its siblings — which is a success, not a failure. Two queries show
the divergence clearly:

- **q09-dpia-trigger**: chunk 0.75 → provision **1.00**. Every relevant rule was found.
- **q12-duo-consent-codes**: chunk 0.33 → provision **1.00**. Same story.
- **q10-broad-consent-validity** moves the other way (0.57 → 0.33): its gold spans three
  distinct sections and only one was reached. Chunk recall was flattering it.

**A data-quality problem this exposed, and fixed.** The first run put
`gdpr-dpia-genomic-research § Further Reading` and `§ News — 2 Sep 2019` in q09's gold
provisions. Those are page furniture from the scraped GA4GH brief, not provisions — the
heading detector was treating the page's navigation `<h2>`s as sections, inflating the
provision count for every fetched HTML document (the GDPR and Taiwan statutes were clean).

`_is_page_furniture` now rejects a small set of navigation labels and anything date-shaped,
including the `News — 2 Sep 2019` pattern of a furniture label joined to a date. Provision
recall@8 rose from 0.715 to **0.729** once the phantom provisions stopped counting against
it. The filter is deliberately a short explicit list rather than a general classifier: it
must never reject a real heading, so `Article 35` and `Timing and structure` are pinned by
tests alongside the rejections.

**Both metrics stay reported.** Chunk recall still measures how much supporting text a
reviewer receives; provision recall measures whether the rule was found at all. The second
is the one to optimise, and the one that survives a change of chunker.

---

## 4e. q02 solved — a tokenizer problem, not a ranking problem

§4c left q02 as the clearest ceiling: the Taiwan withdrawal provision ranked 14th of 207
even with the jurisdiction filter on. Neither fusion nor chunking moved it. Comparing the
query's vocabulary against the provision's explained why in one line:

```
query   : Can participants withdraw ... what happens to retained samples?
Art. 8  : A Participant may ... withdraw ... the Operator shall destroy the
          biological specimens ...
shared content words: {withdraw}
```

**Statutes are written in the singular; questions are asked in the plural.** `tokenize`
did no normalisation, so `participants` and `participant` were unrelated terms, as were
`samples` and `sample`. BM25 had almost nothing to match on.

`fold_plural` folds regular plurals only, protecting `-ss`, `-us` and `-is` endings so
`process`, `status` and `analysis` survive. No verb or comparative stemming: an aggressive
stemmer collides distinct legal terms, and since the same function normalises both query
and corpus, a wrong fold corrupts both sides at once.

| Metric | @1 | @3 | @5 | @8 |
|--------|----|----|----|----|
| chunk-level recall | 0.468 → **0.496** | 0.565 → **0.649** | 0.607 → **0.690** | 0.628 → **0.739** |
| provision-level recall | 0.569 | 0.639 → **0.722** | 0.660 → **0.743** | 0.729 → **0.812** |

**q02 goes from 0.00 to 1.00**, and provision recall@8 gains 8 points overall — the largest
single improvement measured in this phase, from a dozen lines of tokenizer code. Eight of
twelve queries now reach 1.00 provision recall.

The lesson generalises beyond this corpus: for statutory retrieval, matching the register
of the source text matters more than the ranking function. Two ranking heuristics were
measured and rejected (§3b) and a fusion change bought 4 points (§4c); normalising number
agreement bought 8.

---

## 4f. The corpus is now reproducible

`tools/fetch_corpus.py` rebuilds every primary source from its publisher —
`--list`, `--only KEY`, `--check`, `--dry-run`. Previously the corpus was a set of opaque
files nobody could regenerate or audit.

**Every fetch is validated before it is written**, which encodes the §4c failure directly:
a target declares `must_contain` phrases and a `min_words` floor, and content that fails is
reported and *not written*. Given the Singapore table of contents that started this, the
check reports `missing required phrase 'shall not' — likely a table of contents` instead of
silently adding 11,000 words of navigation to the corpus. `--check` re-validates what is
already on disk; all 13 targets currently pass.

---

## 4g. Multi-provision recall — a slot-allocation problem

After §4e, the four remaining weak queries all shared a shape: gold spanning several
provisions, with top-8 reaching one or two. Locating every missing provision in the full
ranking settled what kind of problem it was:

| Query | Missing provisions, by rank |
|-------|-----------------------------|
| q03 | Art. 44 at **34**, Art. 46 at **49**, recitals at **11** |
| q01 | FRS at **9**, GDPR Art. 7 at **14** |
| q10 | recitals at **29** |
| q11 | Consent Policy at **20** |

**Nothing was un-retrieved.** Every missing provision was in the ranking, just past the
cut. So this is not a matching failure, and not a ranking failure either — the ordering is
broadly right. It is a *slot allocation* problem: eight slots, and some were spent on a
second or third fragment of a provision already represented.

Two responses were measured:

| | provision@5 | provision@8 | chunk@8 | P@8 |
|---|---|---|---|---|
| baseline | 0.743 | 0.812 | 0.739 | 0.200 |
| deeper `top_k=12` | — | 0.854 | 0.801 | 0.186 |
| deeper `top_k=20` | — | 0.917 | 0.915 | 0.167 |
| **cap 2 fragments per provision** | 0.743 | **0.854** | 0.725 | 0.200 |
| cap 1 fragment per provision | **0.812** | 0.854 | 0.662 | 0.177 |

**Adopted: at most two chunks per provision.** It reaches the same provision recall as
showing 50% more results, at unchanged precision and with chunk recall essentially flat.
The justification is the product one: a reviewer working through a checklist wants the list
of distinct applicable rules, and a second fragment of an article already on the list costs
a slot a different rule could have used.

Note this is *not* the per-document diversification measured and rejected in §3b. That
capped by document and pushed away same-document gold; this caps by **provision**, which
only exists as a concept since §4d. Same instinct, different granularity, opposite result —
worth stating plainly, because the earlier rejection would otherwise look inconsistent.

`cap=1` is better still at k=5 (0.812) and is available via
`REGBOT_MAX_CHUNKS_PER_PROVISION=1`; it was not made default because dropping chunk recall
to 0.662 leaves a reviewer with less of each rule's text.

All four weak queries improved or held: q01 0.50 → 0.75, q03 0.25 → 0.50, q10 and q11
unchanged at 0.50. **Eight of twelve queries now reach 1.00 provision recall.**

---

## 4h. Corpus audit — reading the chunks one by one

Reviewing actual chunk text rather than aggregate metrics surfaced four defects, one of
them introduced by me. None had shown up in any score.

**1. PDF running headers were being ingested as body text.** Every page of the GA4GH
Consent Policy carries "CONSENT POLICY" as a header, which `pypdf` extracts inline. It
opened most chunks of that document, and one chunk consisted of *nothing but* the header:

```
'\u200b\nC\nONSENT\n P\nOLICY'      ← a 19-character chunk in the index
```

It polluted embeddings, inflated BM25 on a meaningless term, and could be selected as a
chunk's verbatim quote. `_running_lines` now detects short lines repeating on at least half
a document's pages and strips them; long repeated lines are kept, since body text may
legitimately repeat. 48 affected chunks, now 0.

**2. My own Taiwan extractor was corrupting the statute.** Splitting the page text on
`/Article \d+/` also fired on **cross-references inside a provision**:

```
"...referred to in Article 5, Paragraph 3 hereof shall apply..."
        ↓
Article 5                          ← fabricated heading
, Paragraph 3 hereof shall apply…  ← sentence fragment as its "body"
```

Articles 13 and 19 each appeared four times, real provisions were shattered, and the
`section` metadata attributed text to the wrong article. The MOJ page has proper structure —
`div.row` containing `div.col-no` and `div.col-data`, one row per article — so the extractor
now reads that and never guesses. This was a self-inflicted correctness bug that no metric
caught: q02 scored 1.00 while its corpus was corrupt.

**3. Taiwan's two Acts shared an article numbering space.** Both the Human Biobank
Management Act and the Personal Data Protection Act number from Article 1, so a provision
key of `tw-law § Article 8` was ambiguous. They are now separate documents
(`tw-biobank-act`, 31 articles; `tw-pdpa`, 66), which makes every provision key unique.

**4. 44 chunks were bare structural headings.** "Section 2 Information and access to
personal data" as a standalone chunk cites nothing a reviewer can use. A heading with no
body of its own now carries forward to lead the following block.

Plus web navigation ("Latest News", "Our products") and EUR-Lex file metadata
(`L_2016119EN.01000101.xml`) that the fetcher's boilerplate filter had missed.

| | before | after |
|---|--------|-------|
| chunks | 963 | **864** |
| chunks under 200 characters | 110 | **21** |
| bare-heading chunks | 44 | **0** |
| chunks carrying a PDF running header | 48 | **0** |
| Taiwan chunks | 207 (one document) | 135 (two Acts) |

The `after` column includes a second pass over the 26 short chunks the first one left. Two
were not content — a bare `9 Appendix 2` page label and the fetcher's own provenance line,
now written as a footer so it stops leading the document's first chunk — which took the
corpus to 864. The 21 that remain were each read and kept deliberately: real provision text,
footnotes, and bibliography entries from the FRS appendix.

Retrieval barely moved — provision recall@5 rose 0.743 → 0.787, @8 held at 0.846 — which is
the point worth recording: **none of these defects were visible in the metrics.** A cleaner
corpus mostly buys correct citations, and the Taiwan bug would have produced a confidently
mislabelled article reference in a report meant for regulatory review.

**Corpus balance is still uneven and that is expected**, not a defect: GDPR contributes 504
chunks and Taiwan 135 because those are the two jurisdictions on real statute, while
Singapore, Japan, Hong Kong, Korea and China are still ~5-chunk contributor summaries. The
imbalance is a direct measure of how much of the corpus has been migrated, and it will even
out only when the remaining five are replaced.

---

## 5. The benchmark was not reproducible (and the fix)

Running `python -m src.main benchmark` three times with no changes produced **three
different scores**:

```
R@5=0.7024  R@8=0.8552  MRR@8=0.8333
R@5=0.7093  R@8=0.8413  MRR@8=0.8361
R@5=0.7024  R@8=0.8552  MRR@8=0.8333
```

At the time, a ±1.4-point swing in recall@8 made the candidate-pool sweep hard to trust:
the winning configuration beat the baseline by 4.2 points, only about three times the
noise. It also made `--min-recall` unusable as a CI gate, since a gate that fails at random
is worse than none. (§2 has since been re-run on the fixed retriever; the figures published
there are the deterministic ones.)

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

§2 has been re-run on the fixed retriever and its numbers supersede the earlier noisy ones.
The original conclusion held and strengthened: the lexical-weighted config's advantage over
the old default grew from 4.2 to 7 points of recall@8 once the noise was removed.

---

## 6. Threats to validity

Stated plainly, because the numbers look better than the evidence supports:

1. **The gold set is self-labelled.** Written by the same contributor who tuned the
   retriever. Needs mentor review before it means anything externally.
2. **12 queries on 91 chunks.** A 4-point recall difference is roughly one chunk moving in
   one query. The adopted config is a reasonable default, not a settled result.
3. ~~**20 of 22 documents are contributor-authored summaries.**~~ **Addressed in §4b** —
   P0/P1 are now primary sources (96% of chunks). P2 regional law remains summarised by
   design and is marked `content_type: summary` in the data and in both UIs. The residual
   threat is smaller but real: those 8 summary documents still carry the contributor's
   phrasing, and the six regional queries are scored against them.
4. **Anchors resolve more broadly than intended.** With 150-char chunk overlap, a phrase
   like `Recital 33` matches adjacent chunks, so some queries have larger gold sets than
   hand-specified (q10: 7 chunks from 3 anchors). This deflates recall slightly — a
   conservative bias, but not a deliberate one.
5. **No re-ranker was tested.** The proposal listed it as conditional ("if beneficial").
   Given the failure mode is recall spread across chunks rather than mis-ranking, a
   cross-encoder would likely not fix q10/q11 — it reorders a candidate list that is
   already missing the gold chunks.

## 7. Next steps

- [ ] Mentor review of the gold set — the blocking item.
- [ ] Expand to ~30 queries, weighted toward unfiltered multi-chunk topics.
- [ ] Revisit sibling boost (§3b) once the gold set is larger and reviewed — it looks
      promising for recall@5 but is not separable from noise at n=12.
- [x] ~~Replace contributor summaries with primary statutory text~~ — done, §4b.
      Recall fell 0.876 → 0.684 as predicted.
- [x] ~~Filter scoping~~ and ~~heading-aware chunking~~ — done, §4c. The scoping hypothesis
      was wrong; max fusion was the actual fix.
- [x] ~~Provision-level recall~~ — done, §4d.
- [x] ~~q02 ceiling~~ — solved in §4e; it was a tokenizer problem (0.00 → 1.00).
- [x] ~~Filter page furniture out of headings~~ — done, §4d.
- [x] ~~Move the corpus fetchers into the repo~~ — done, §4f (`tools/fetch_corpus.py`).
- [x] ~~Multi-provision recall~~ — partly addressed in §4g (0.812 → 0.854).
- [ ] q03, q10, q11 still sit at 0.50: their remaining provisions rank 20-49, too deep for
      slot reallocation to reach. These need better ranking, not better allocation — a
      cross-encoder re-ranker over the fused pool is now worth the experiment §3b deferred,
      because the candidates *are* present.
- [ ] HK, KR: official text needs a JavaScript-capable fetch. SG, JP: the sites serve a
      table of contents; the operative text needs a different entry point.
- [ ] Re-run `benchmark` and re-review the gold set on **every** corpus change (see §4).
- [ ] Wire `benchmark --min-recall` into CI as a regression gate once the gold set is
      approved. Now viable: the benchmark is reproducible (§5), so the gate will not flake.
      Currently passes at 0.85.
- [ ] Reconsider `precision@k`'s denominator. Dividing by results returned (§1) is right
      for jurisdiction-filtered queries but rewards configurations that return fewer
      results, as §3b showed. Reporting `returned` alongside is a partial mitigation;
      reporting both denominators would be better.
