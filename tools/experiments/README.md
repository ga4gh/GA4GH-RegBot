# Retrieval experiments and the consent → provision benchmark

Research tooling that sits beside the product code. Nothing here is imported by `src/`;
everything reads the same store (`data/regbot_store`) and the same gold sets, and every
script is deterministic for a given seed. Heavy model runs are cached under
`~/.cache/regbot/`.

## Retrieval ablations (41-query gold set)

| script | what it does |
|---|---|
| `ablate.py` | Re-implements the production retriever with every design decision exposed (fusion rule, plural folding, scope-local IDF, per-provision cap, pool sizes, contextual headers, dense encoder, cross-encoder) and scores each variant with per-query paired tests (`src/regbot/significance.py`). Its `baseline` reproduces `python -m src.main benchmark` bit for bit. Suites: `core`, `models`, `rerank`. |
| `multi_aspect_pilot.py` | Concatenates *m* gold questions into one query and measures how provision recall falls with *m* — the shape of a consent form sent as a single query. |

## Consent → provision benchmark

The task: given a consent form and a set of jurisdictions, retrieve the provisions that
govern each governance aspect the form raises. Gold is a *crosswalk* of
(aspect × jurisdiction) cells, each judged once, so any consent form can be scored after
clause-level aspect labelling alone.

| file | role |
|---|---|
| `../../examples/eval/crosswalk/aspects.yaml` | 16-aspect taxonomy with participant-facing cues and statute-register queries |
| `../../examples/eval/crosswalk/document_roles.yaml` | law / policy / guidance / template / summary for every corpus document |
| `../../examples/eval/crosswalk/ANNOTATION_GUIDE.md` | labelling rules and procedure |
| `pool_candidates.py` | `pool`: TREC-style candidate pooling over heterogeneous retrievers (per provision; per chunk for unstructured documents, see `units.py`); `anchors`: judged pool → gold anchors (`--llm-model` for a silver standard) |
| `annotate.html` | local keyboard annotation tool; labels autosave in the browser and export as JSON |
| `prelabel.py` | LLM pre-labels through Ollama, cached; `agreement.py` reports Cohen's κ between two label files |
| `fetch_consent_docs.py` | downloads the consent documents with their stated reuse terms (run with `python -I`) |
| `consent_docs.py` | `draft`: freeze clause segmentation by hash and propose aspects; `review` / `stats` |
| `aspect_clf_eval.py`, `aspect_clf_llm.py` | clause → aspect classifiers scored against the gold clause labels (zero-shot prototypes, leave-one-document-out logistic regression, local LLM) |
| `consent_pipeline.py` | Decompose → Bridge → Allocate, the whole-form and decompose-only baselines, template channel, gap candidates; `segments` and `demo` subcommands |
| `consent_eval.py` | scores systems × scopes × budgets: provision recall, cell coverage, precision, template rate, gap P/R, clause-aspect F1 |

### Rebuilding from scratch

```bash
python -I tools/experiments/fetch_consent_docs.py              # consent documents
python tools/experiments/consent_docs.py draft                  # clause texts + proposals (labels kept)
python tools/experiments/pool_candidates.py pool --aspects examples/eval/crosswalk/aspects.yaml \
    --roles examples/eval/crosswalk/document_roles.yaml --out pool.json
python tools/experiments/prelabel.py --pool pool.json --model qwen3:14b --depth 5
# judge in annotate.html, export crosswalk_labels.json, then:
python tools/experiments/pool_candidates.py anchors --pool crosswalk_labels.json \
    --out examples/eval/crosswalk/crosswalk_gold.yaml --version 0.1
python tools/experiments/consent_eval.py --crosswalk examples/eval/crosswalk/crosswalk_gold.yaml \
    --docs examples/eval/consent_docs.yaml --aspects oracle --out results.json
```

The newer encoders need the pinned `requirements.txt` stack; a separate venv built from it
(`.venv-exp`) is used for `--suite models` and for pooling.
