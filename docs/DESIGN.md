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
| `src/regbot/study_type.py` | Lightweight routing hints (trial, biobank, cohort, genomic) |
| `src/main.py` | `RegBot` façade; CLI (`ingest`, `check`, `status`, `eval`) |
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

| Parameter | Location | Phase 2 tuning |
|-----------|----------|----------------|
| `top_k` | CLI / UI | Trade recall vs noise on gold queries |
| Semantic / BM25 pool | `retrieval.py` | Balance lexical vs semantic retrieval |
| Chunk size / overlap | `text_utils.chunk_text` | Jurisdiction-specific PDF structure |
| `category` / `jurisdiction` filter | ingest metadata | Cross-border queries scoped to relevant law |
| Re-ranker | — | Add only if retrieval quality improves on the gold set |

---

## 3. Data Model

### 3.1 Chunk record (`manifest.json`)

Each ingested unit is addressable for retrieval, BM25, and citation verification.

**Implemented today:**

```json
{
  "id": "<source_hash>_p<page>_c<index>",
  "text": "<chunk body>",
  "metadata": {
    "source": "<filename>",
    "source_path": "<absolute path>",
    "page": 0,
    "category": "<stem or ingest label>"
  }
}
```

**Phase 1 target schema** (mentor-agreed; populate when extractable):

| Field | Required | Description |
|-------|----------|-------------|
| `document_id` | yes | Stable corpus id, e.g. `ga4gh-frs`, `gdpr-art9-brief` |
| `jurisdiction` | yes* | Governance scope for filtering (*`GA4GH` / `EU` for framework docs) |
| `section` | optional | Heading or clause id from PDF structure |
| `framework` | optional | e.g. `GA4GH`, `REWS`, `GDPR`, `national` |
| `ingested_at` | yes | ISO 8601 timestamp |
| `source`, `page`, `category` | yes | As today |

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

Output is a **navigation aid**, not a compliance certificate.

**Current shape** (see README for env-driven behaviour):

```json
{
  "study_type": "genomic_research",
  "status": "Partially Compliant",
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

**Phase 3 extensions**—nested under each recommendation as `evidence[]`:

| Field | Purpose |
|-------|---------|
| `chunk_id` | Same allow-list as today |
| `source`, `page` | From chunk metadata |
| `quote` | Short verbatim span from chunk text |
| `relevance` | Why this clause matters for the uploaded study text |
| `jurisdiction` | Copied from chunk metadata for reviewer orientation |
| `governance_hint` | Optional pointer to institutional role (DPO, IRB, DAC)—**informational only** |

**Report-level flags (Phase 3):**

```json
{
  "needs_human_review": true,
  "review_reason": "weak_retrieval | low_overlap | grounding_failed"
}
```

Set when retrieval is empty, overlap drops all recommendations, or grounding fails after retries.

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

**Gold set:** Mentor-reviewed `(query, expected_chunk_ids[], optional jurisdiction)` pairs from the real corpus. Start from `examples/eval/queries_ga4gh.txt` and extend with jurisdiction-relevant probes as the corpus grows.

**Metrics:**

| Metric | Use |
|--------|-----|
| **Recall@k** | Primary; are gold chunks in top-k? |
| **Precision@k** | Noise in top-k for reviewers |
| **MRR** | Rank of first relevant chunk |

**Procedure**

1. Ingest corpus with agreed metadata (`ingest --reset` per benchmark run).
2. Use and extend the `eval` harness to compare retrieval output against the gold set.
3. Tune chunking, fusion, `top_k`, and optional re-ranker; document baseline vs improved runs for mentor review.
4. Keep a small frozen subset in CI (mocked embeddings); run the full benchmark manually or on a schedule.

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

- No secrets or `data/regbot_store/` in git; local-first processing unless operator opts into cloud LLM.
- UI and exports carry **not legal advice** disclaimer.
- Chroma telemetry off by default.
