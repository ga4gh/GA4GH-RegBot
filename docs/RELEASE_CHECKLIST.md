# GA4GH-RegBot 0.1.0 release checklist

Status as of 2026-08-10. This checklist separates completed contributor verification from
independent review that must not be self-certified.

## Complete

- [x] Scope-complete 85-document corpus; fetch validation passes for all 83 reproducible targets.
- [x] PDF running headers, recognized front matter, and audited extraction splits cleaned.
- [x] Exact dense retrieval, scope-local BM25, deterministic fusion, and provision diversity.
- [x] 41-query gold v0.8 resolves completely against the benchmarked 4,416-chunk,
      51-document store snapshot; the 8,081-chunk, 85-document v0.6 corpus awaits
      mentor-reviewed evaluation.
- [x] Final contributor-labelled benchmark recorded in `docs/eval_results.md`.
- [x] LLM and offline paths enforce chunk allow-lists and token-overlap checks.
- [x] Any unsupported offline recommendation is dropped and escalated for human review.
- [x] Local Ollama `llama3` end-to-end path validated, including proxy-safe localhost access.
- [x] FastAPI, Next.js, CLI, tests, lint, type checks, and production build verified.
- [x] Web/API login issues signed sessions; optional public-user access is read/review-only,
      with ingest, reset, and custom-store access enforced as administrator-only.
- [x] Client-selected chat evidence is resolved against the active store; manifests and API
      responses contain no server filesystem paths.
- [x] Frontend dependency graph updated to Next.js 16.3.0 and patched transitive versions;
      `npm audit` reports zero vulnerabilities on 2026-08-10.
- [x] Version and user/developer/demo documentation updated for `0.1.0`.

## Intentionally pending

- [ ] Independent mentor review of `examples/eval/gold_ga4gh.yaml`.
- [ ] After approval, select an agreed regression threshold and enable it for the scheduled
      benchmark. The workflow already accepts a manual `min_recall` input; its default is
      report-only so contributor labels cannot become a release claim by accident.

No commit, tag, push, merge, or release publication is performed by this checklist.
