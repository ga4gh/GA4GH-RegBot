# Google Summer of Code — Design Document

## 1. Overview

**Problem.** Cross-border genomic research depends on fragmented, jurisdiction-specific frameworks. Researchers spend significant time locating the right clauses, institutional contacts, and accountability pathways across GA4GH guidance, REWS materials, GDPR-related briefs, and regional data-protection law.

**Product.** GA4GH-RegBot is an open-source, **AI-assisted regulatory navigation** tool. Researchers provide study materials—protocol excerpts, consent / data-use language, data-flow descriptions. RegBot retrieves applicable provisions from a **curated regulatory corpus** and returns a **structured navigation document** (clause-linked recommendations, citations, and—where metadata supports it—governance touchpoints).

**Boundary.** RegBot **does not** issue compliance decisions or approvals. It surfaces evidence for **human governance review** (DPOs, IRBs, Data Access Committees). It processes only regulatory texts and researcher-supplied documents—**no patient-level data**.

**Design principles**

| Principle | Implementation |
|-----------|----------------|
| Citation-grounded | Chunk-ID allow-list + token-overlap filter (see §3) |
| Fail safe | Low-confidence / weak retrieval → flag for human review, not forced answers |
| GA4GH fit | Complements REWS / Regulatory & Ethics Toolkit; does not replace committees |

**GSoC 2026 focus:** real corpus + `jurisdiction` metadata (§3), measured hybrid retrieval (§4), richer evidence in JSON reports, Streamlit polish. **Out of scope:** legal verdicts, hosted multi-tenant service, FHIR integration, public benchmark dataset, `pip` API (post-GSoC).

---

## 2. System Architecture

### 2.1 End-to-end flow

RegBot follows three layers aligned with the GSoC proposal—each targets a known failure mode of naive RAG on legal text.

```
  RESEARCHER INPUTS                    REGULATORY CORPUS
  (consent, DUL, protocol excerpts)    (GA4GH, REWS, GDPR briefs, regional law)
              │                                    │
              └──────────────┬─────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1 — INGEST & INDEX                                                   │
│  PDF / TXT → parse → metadata-aware chunks → embed → persist               │
│  Chroma (vectors) + manifest.json (full text + metadata for BM25 / audit) │
└────────────────────────────────────────────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ LAYER 2 — HYBRID RETRIEVAL                                                 │
│  Query (+ optional jurisdiction / category filter)                         │
│  Dense (SentenceTransformers) ∥ BM25 → RRF → top-k                         │
│  [Phase 2: optional re-ranker on candidate pool]                           │
└────────────────────────────────────────────────────────────────────────────┘
                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ LAYER 3 — GROUNDED GENERATION                                              │
│  LLM (Ollama default / OpenAI optional) → structured JSON                  │
│  [1] chunk_id allow-list → retry if hallucinated                             │
│  [2] token-overlap filter → drop / retry low-support rows                  │
│  [3] insufficient-evidence path → needs_human_review (Phase 3)             │
│  Fallback: keyword heuristic when LLM unavailable                          │
└────────────────────────────────────────────────────────────────────────────┘
                             ▼
              STRUCTURED NAVIGATION DOCUMENT (JSON + UI export)
              → human review by DPO / IRB / DAC
```

Low-confidence cases **escalate upward** in the diagram: weak retrieval or failed grounding should prefer `Unknown` / `needs_human_review` over speculative citations.

### 2.2 Module map

| Path | Role |
|------|------|
| `src/regbot/ingestion.py` | Parse PDF/txt, chunk, embed, write Chroma + `manifest.json` |
| `src/regbot/retrieval.py` | `HybridRetriever`: dense + BM25 + RRF; metadata filters |
| `src/regbot/fusion.py` | Reciprocal rank fusion |
| `src/regbot/compliance.py` | LLM JSON report, retries, offline fallback, follow-up Q&A |
| `src/regbot/grounding.py` | Allow-list audit, token overlap, normalization |
| `src/regbot/evidence.py` | Phase 3: `evidence[]` enrichment, quote selection, human-review escalation |
| `src/regbot/evaluation.py` | Phase 2: gold-set anchors, Recall@k / Precision@k / MRR |
| `src/regbot/study_type.py` | Lightweight routing hints (trial, biobank, cohort, genomic) |
| `src/main.py` | `RegBot` façade; CLI (`ingest`, `ingest-manifest`, `check`, `status`, `eval`, `benchmark`) |
| `src/api/app.py` | FastAPI layer for the Next.js UI |
| `src/streamlit_app.py` | Upload, analyse, export, exploratory chat on last retrieval |

### 2.3 Technology stack

| Layer | Choice | Notes |
|-------|--------|--------|
| Runtime | Python 3.10–3.12 (CI: 3.11) | See README for venv / deps |
| Embeddings | `all-MiniLM-L6-v2` (configurable) | HF download on first ingest |
| Vector store | Chroma (local persistent) | Telemetry off by default |
| Lexical | BM25 over manifest | Rare legal terms (“pseudonymisation”, etc.) |
| Fusion | RRF | No score calibration across dense vs sparse |
| LLM | Ollama (default) / OpenAI | OpenAI-compatible client for both |
| UI | Streamlit | Phase 4: evidence display + export polish |

Core path does **not** depend on LangChain/LlamaIndex adapters.

### 2.4 Retrieval parameters (tuning surface)

| Parameter | Location | Phase 2 outcome |
|-----------|----------|-----------------|
| `top_k` | CLI / UI | **8** — recall saturates at 12 while precision decays monotonically |
| Semantic / BM25 pool | `config.py` | **12 / 48** — lexical weighting won on both recall and precision |
| Chunk size / overlap | `text_utils.chunk_text` | Unchanged (900 / 150); overlap widens anchor resolution |
| `category` / `jurisdiction` filter | ingest metadata | Filtered queries reach recall 1.00 |
| Re-ranker | — | **Not adopted** — failure mode is missing candidates, not mis-ranking |

Measured results and the reasoning behind each choice: [`eval_results.md`](eval_results.md).
Pool sizes are overridable via `REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES`.

---

## 3. Data Model

### 3.1 Chunk record (`manifest.json`)

Each ingested unit is addressable for retrieval, BM25, and citation verification.

**Implemented today** (all 128 chunks carry every field below except `content_type`,
which is set from the corpus manifest):

```json
{
  "id": "<source_hash>_p<page>_c<index>",
  "text": "<chunk body>",
  "metadata": {
    "source": "<filename>",
    "source_path": "<absolute path>",
    "page": 0,
    "category": "<stem or ingest label>",
    "document_id": "ga4gh-frs",
    "jurisdiction": "GA4GH",
    "framework": "GA4GH",
    "content_type": "primary"
  }
}
```

**Phase 1 schema status:**

| Field | Status | Description |
|-------|--------|-------------|
| `document_id` | ✅ implemented | Stable corpus id, e.g. `ga4gh-frs`, `gdpr-dpia-genomic-research` |
| `jurisdiction` | ✅ implemented | Governance scope for filtering (`GA4GH` / `EU` for framework docs) |
| `framework` | ✅ implemented | e.g. `GA4GH`, `REWS`, `GDPR`, `national` |
| `content_type` | ✅ implemented | `primary` (source regulatory text) or `summary` (contributor paraphrase) |
| `source`, `page`, `category` | ✅ implemented | As before |
| `section` | ❌ **not implemented** | Heading / clause id from PDF structure — needs a structure-aware parser; `pypdf` text extraction does not preserve headings |
| `ingested_at` | ⚠️ manifest only | Recorded per document in `corpus_manifest.yaml`, not copied onto chunks |

**`content_type` and why it exists.** Only `ga4gh-frs` and `ga4gh-consent-policy` are
primary source documents. The other 20 corpus entries are ~300–450-word contributor-written
paraphrases. A citation to a paraphrase is **not** a citation to the underlying clause, so
the distinction must be machine-readable rather than left to a disclaimer inside the text.
Replacing summaries with primary text where licensing permits is the top corpus priority.

#### Jurisdiction vocabulary (REWS regional scope)

Initial corpus tagging aligns with East Asia / cross-border sharing priorities discussed with mentors. Use **normalized codes** on every chunk; free-text country names only in `notes` if needed.

| Code | Representative legal basis (corpus labels, not legal advice) |
|------|----------------------------------------------------------------|
| `SG` | PDPA 2012, HBRA, Health Information Bill |
| `CN` | Human Genetic Resources Regulation; PIPL; Data Security Law |
| `TW` | Human Biobank Management Act; PDPA |
| `KR` | Bioethics and Safety Act; PIPA; AI framework (2025/26) |
| `JP` | Ethical Guidelines for Medical/Health Research; APPI; Act on Promotion of Genomic Medicine (2023) |
| `HK` | Personal Data (Privacy) Ordinance; cross-border transfer (s.33) |
| `EU` | GDPR and related briefs (where redistributable) |
| `GA4GH` | GA4GH / REWS framework documents (international norms) |
| `INTL` | Cross-cutting GA4GH guidance not tied to one member state |

**Query behaviour:** optional `jurisdiction` (and `category`) filters narrow retrieval to relevant law. Multi-jurisdiction analysis in a single pass remains post-GSoC; Phase 1 focuses on metadata that makes scoped retrieval possible.

**Corpus inventory:** [`docs/corpus_manifest.yaml`](corpus_manifest.yaml) (Phase 1)—per document: `document_id`, `jurisdiction[]`, version, URL, license, ingest date. No vector stores in git.

### 3.2 Compliance / navigation report (JSON)

Output is a **navigation aid**, not a compliance certificate. The `coverage` field describes topic completeness for human review—not a compliance ruling.

**Current shape** (see README for env-driven behaviour):

```json
{
  "study_type": "genomic_research",
  "coverage": "partial",
  "missing_elements": ["..."],
  "recommendations": [
    {
      "text": "...",
      "evidence_chunk_ids": ["<id-from-retrieval-only>"]
    }
  ],
  "citations": [{ "chunk_id": "...", "reason": "..." }],
  "notes": "...",
  "grounding": {
    "ok": true,
    "issues": [],
    "overlap": {
      "kept_count": 1,
      "dropped_count": 0,
      "dropped_all": false,
      "min_threshold": 0.06
    }
  },
  "grounding_attempts": 1
}
```

**Phase 3 extensions — implemented** ([`evidence.py`](../src/regbot/evidence.py)), nested
under each recommendation as `evidence[]`:

| Field | Purpose |
|-------|---------|
| `chunk_id` | Same allow-list as before |
| `resolved` | `false` when a cited id is not in the retrieved set — the entry is kept, not dropped, so `evidence[]` never silently disagrees with `evidence_chunk_ids` |
| `source`, `page` | From chunk metadata |
| `document_id`, `framework` | From chunk metadata |
| `quote` | Short **verbatim** span selected from chunk text by token overlap — never model-generated |
| `relevance` | **Mechanical** statement of the lexical link ("Shares terminology: …") |
| `jurisdiction` | Copied from chunk metadata for reviewer orientation |
| `governance_hint` | Pointer to the body that normally reviews this scope (DPO, IRB, DAC) — **informational only** |

Two constraints follow directly from the grounding contract (§3.3):

- **`quote` is verbatim.** A paraphrased quote would be a new ungrounded assertion sitting
  inside the block whose whole purpose is traceability.
- **`relevance` is mechanical, not interpretive.** An LLM-authored rationale ("this clause
  matters because…") is exactly the kind of unverifiable claim the allow-list exists to
  prevent. Stating the lexical link lets a reviewer judge relevance themselves.

**Report-level flags (implemented):**

```json
{
  "needs_human_review": true,
  "review_reason": "weak_retrieval",
  "review_reasons": ["weak_retrieval", "grounding_failed"],
  "review_details": "Retrieval returned 0 chunk(s); there is not enough policy context…"
}
```

Set when retrieval is empty (`weak_retrieval`), grounding fails after retries
(`grounding_failed`), or the overlap filter drops every recommendation (`low_overlap`).
When several fire, `review_reason` reports the one that explains the others
(weak retrieval → grounding failure → low overlap); `review_reasons` keeps the full set.
The offline keyword fallback marks overlap as `skipped`, which is deliberately **not** a
review trigger — it means the filter did not run, not that support was weak.

### 3.3 Grounding contract (invariants)

These rules are **code-enforced** on the LLM path:

1. `evidence_chunk_ids` and `citations[].chunk_id` ⊆ retrieved chunk ids for this request.
2. Violations → automatic retry with explicit allow-list (`max_grounding_retries`).
3. Token recall vs cited chunk texts ≥ `REGBOT_MIN_TOKEN_OVERLAP` (default `0.06`); drops recorded in `grounding.overlap`.
4. Offline keyword fallback: overlap skipped; chunk-id audit where ids exist.

---

## 4. Evaluation Plan

### 4.1 Objectives

| Phase | Question answered |
|-------|-------------------|
| 2 | Does hybrid retrieval return the **right clauses** for mentor-approved queries? |
| 3 | Are reports **reviewable**—grounded, with evidence spans, and honest about uncertainty? |

### 4.2 Retrieval benchmark (Phase 2)

**Gold set:** [`examples/eval/gold_ga4gh.yaml`](../examples/eval/gold_ga4gh.yaml) — 12
queries with `(query, relevant[], optional jurisdiction)`. **Drafted, not yet
mentor-reviewed.**

Labels are **anchors** (`document_id` + `contains` phrase), not literal `chunk_id`s: chunk
ids embed a hash of the absolute ingest path, so an id recorded on one machine never
resolves on another. Anchors resolve against the live manifest at benchmark time, which
keeps the gold set portable across re-ingests and contributors. An anchor matching nothing
is reported as `unresolved_anchors`; a query whose anchors all fail is **skipped rather
than scored**, so a stale gold set fails loudly instead of inflating recall.

**Metrics:**

| Metric | Use |
|--------|-----|
| **Recall@k** | Primary; are gold chunks in top-k? |
| **Precision@k** | Noise in top-k for reviewers |
| **MRR** | Rank of first relevant chunk |

**Procedure**

1. Ingest the corpus: `python -m src.main ingest-manifest --reset`.
2. Score retrieval: `python -m src.main benchmark --gold examples/eval/gold_ga4gh.yaml`.
3. Tune via `REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES` / `top_k`; record runs
   in [`eval_results.md`](eval_results.md).
4. `--min-recall` exits non-zero below a threshold, so the benchmark can gate CI once the
   gold set is approved. Metric logic is unit-tested with a stub retriever
   (`tests/test_evaluation.py`), so CI needs no embedding model.

**Re-review the gold set on every corpus change.** Growing the corpus from 13 to 22
documents silently invalidated v0.1: newly ingested briefs were topically relevant to
existing queries, retrieval ranked them first, and the stale gold set scored those correct
hits as misses — a labelling artefact that looked like a code regression. See
[`eval_results.md` §4](eval_results.md).

### 4.3 Report quality (Phase 3)

| Check | Method |
|-------|--------|
| Allow-list never violated | `tests/test_grounding.py` + integration fixtures |
| `evidence[]` populated when chunks exist | JSON schema test on golden outputs |
| `needs_human_review` on empty / weak retrieval | Synthetic consent + empty store |
| No overlap regression | `tests/test_overlap.py` |

---

## 5. Corpus & Operations

### 5.1 Corpus scope (Phase 1)

| Tier | Content |
|------|---------|
| **P0** | GA4GH Framework for Responsible Sharing; priority REWS guidance |
| **P1** | GDPR / consent-code **briefs** where license permits ingest instructions |
| **P2** | Regional excerpts tagged per §3.1 (`SG`, `CN`, `TW`, `KR`, `JP`, `HK`)—text-native PDFs or mentor-provided exports |

Excluded from public repo: private DUL templates; scanned PDFs without OCR (ingest fails with guidance).

### 5.2 Security & ops

- No secrets in git. Local-first processing unless the operator opts into a cloud LLM.
- **Vector store:** `data/regbot_store/chroma/` is git-ignored — it is regenerable binary
  that rewrites wholesale on every ingest (~3.7 MB of churn per run).
  `data/regbot_store/manifest.json` **is** tracked: it is text, diffable, and serves as
  both the BM25 corpus and the citation-audit record. Rebuild vectors with
  `python -m src.main ingest-manifest --reset`.
- UI and exports carry a **not legal advice** disclaimer.
- Chroma telemetry off by default.
