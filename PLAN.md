# GA4GH-RegBot GSoC 2026 Implementation Plan (Draft)

## Objective
Build a citation-grounded assistant that helps map consent and policy text to relevant GA4GH guidance, and produce a structured gap report for human review.

## MVP Scope
1. Ingest selected GA4GH reference documents.
2. Retrieve relevant clauses for user-provided text sections.
3. Generate grounded responses with strict evidence citations.
4. Export a machine-readable gap report (`JSON`) and readable summary (`Markdown`).

## Architecture (MVP)
- Core language: Python
- Retrieval: embeddings + vector index (initial single choice, then iterate)
- Generation: LLM response layer constrained to retrieved evidence
- Interface: minimal CLI or Streamlit flow for demo

## Deliverables
1. Working ingestion and retrieval pipeline.
2. Citation-grounded response generation.
3. Gap report export pipeline.
4. Tests for ingestion, retrieval, and response contracts.
5. Documentation for setup, architecture, limitations, and future roadmap.

## Evaluation Plan
- Retrieval quality on curated examples (precision@k, recall@k).
- Citation faithfulness and hallucination checks.
- Human review usefulness feedback from mentors/contributors.

## Timeline (Draft)
### Community Bonding
- Finalize MVP documents, schema, and evaluation dataset.
- Confirm mentor expectations and acceptance criteria.

### Phase 1
- Implement ingestion and indexing baseline.
- Validate retrieval quality on small benchmark set.

### Phase 2
- Implement grounded generation with citation checks.
- Add confidence scoring and failure-safe responses.

### Phase 3
- Implement report export, improve usability, and add tests.
- Prepare reproducible benchmark script and docs.

### Final
- End-to-end demo, benchmark summary, and handover notes.

## Out of Scope (MVP)
- Full legal interpretation automation.
- Complete multi-jurisdiction coverage.
- Production-grade multi-tenant access controls.

## Open Questions for Mentors
1. Which GA4GH documents are mandatory for phase 1?
2. Preferred benchmark format for regular review?
3. Priority use cases for the final demo workflow?
