# Crosswalk annotation guide (v0.1, draft)

You are judging, for one **cell** = (governance aspect × jurisdiction), whether each pooled
passage is a provision that a DPO, IRB or DAC reviewer in that jurisdiction would need to
consult when a consent form addresses that aspect.

Aspects and their scope are defined in [`aspects.yaml`](aspects.yaml). Read an aspect's
`definition` before its first cell, and judge against the definition, not against the two
pooling queries shown under it — the queries only generated candidates.

## Labels

| Label | Meaning | Test |
|---|---|---|
| **2 — operative** | The passage itself states a rule, right, duty, prohibition, condition or procedure on this aspect that applies in this jurisdiction. | Would the reviewer cite this passage in a review note on this aspect? |
| **1 — related** | On topic but not operative: a definition the operative rule depends on, a recital or preamble explaining it, an exception cross-referenced from elsewhere, or a rule on a neighbouring aspect. | Useful context, but the reviewer would cite something else. |
| **0 — not relevant** | Different topic, or only shares vocabulary. | — |

Only **2** enters the gold standard by default (`anchors --min-label 2`); **1** is kept so
graded metrics can be reported.

## Rules for hard cases

1. **Judge the passage, not the document.** A highly relevant law can contain irrelevant
   passages; label the passage shown.
2. **Fragments.** If the passage is part of an operative provision but cut mid-sentence,
   label it as the provision it belongs to (usually 2) and add a note `fragment`.
3. **Guidance and soft law** (EDPB guidelines, OECD/UNESCO/WHO, GA4GH briefs) can be **2**
   when they state what must or should be done on this aspect. Their `role` tag is
   recorded, so law-only results can still be reported.
4. **Definitions** (e.g. "pseudonymisation means…") are **1**, unless the aspect is itself
   about that concept and no operative rule is pooled for it, in which case note
   `definition-only`.
5. **Translations.** Judge reference translations the same as primary text; do not penalise
   wording.
6. **Wrong jurisdiction.** Cells are filtered by jurisdiction, but GA4GH/INTL instruments
   are not law anywhere; judge them as applying to their own cell only.
7. **Empty cells.** If after judging every candidate none is a **2**, decide whether the
   jurisdiction genuinely has no provision on this aspect in the corpus. If yes, tick
   *no provision in the corpus* (`e`). If you believe a provision exists but the pool missed
   it, leave the cell unticked and add a note `pool-miss: <document, article>` — these notes
   measure pool completeness and are reported.
8. **Uncertain.** Pick the lower label and add a note `unsure: <reason>`. Disagreement
   analysis uses these.
9. **Seeded candidates.** Candidates carrying a `seed` field (shown at depth 0) come from the
   anchors of the 41-query gold set (`gold_query_aspects.yaml` maps each query to its aspect).
   They were labelled operative for a *question*, not for the cell; judge them against the
   cell's aspect definition like any other candidate.

## Procedure

1. Serve and open the tool:

   ```bash
   cd ~/Desktop/GSoC/05_Paper && python -m http.server 8765
   ```

   Copy `tools/experiments/annotate.html` next to the pool, then open
   `http://localhost:8765/annotate.html?pool=crosswalk_pool_v0.2.json`.
2. Set **depth ≤ 5** (about 2,800 judgments over 144 cells; median 20 per cell). Keep **blind** ticked for the first pass; the pre-labels of two local models (llama3-8B, Qwen3-14B) appear when it is unticked.
3. Work cell by cell. Keys: `2` `1` `0` label and advance, `j`/`k` move, `n` next unlabelled,
   `]`/`[` next/previous cell, `e` empty cell, `/` note.
4. Export regularly (labels also autosave in the browser), then:

   ```bash
   python tools/experiments/pool_candidates.py anchors --pool crosswalk_labels.json \
       --out examples/eval/crosswalk/crosswalk_gold.yaml --version 0.1
   ```

## Agreement

A second annotator labels a stratified 20% of cells (every aspect and jurisdiction at least
once) blind to the first annotator's labels. Report Cohen's κ on the 3-way labels and on the
binarised (2 vs. other) labels, plus the confusion matrix. Disagreements are adjudicated
together, and the adjudication notes are kept with the gold file.
