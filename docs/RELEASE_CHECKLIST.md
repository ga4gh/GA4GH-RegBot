# GA4GH-RegBot 0.1.0 release checklist

Status as of 2026-09-20. This checklist separates completed contributor verification from
independent review that must not be self-certified.

## Complete

- [x] Scope-complete 85-document corpus; fetch validation passes for all 83 reproducible targets.
- [x] PDF running headers, recognized front matter, and audited extraction splits cleaned.
- [x] Exact dense retrieval, scope-local BM25, deterministic fusion, and provision diversity.
- [x] Gold v0.9 resolves all 56 anchors across 41 queries against the 8,078-chunk,
      85-document v0.6 store; any unresolved or partially unresolved query now fails the CLI.
- [x] Full-corpus contributor-labelled engineering benchmark recorded in
      `docs/eval_results.md`: provision recall@8 0.9102, chunk recall@8 0.7110, MRR@8 0.5992.
- [x] Current clean-store rebuild completed without errors; two independent benchmark
      processes returned identical JSON, and the stricter 0.911 negative control failed.
      The earlier four-run record is retained with the historical poster snapshot.
- [x] Scheduled benchmark enforces the internal regression floor
      `provision_recall@8 >= 0.90` and uploads its report.
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
- [x] Updated pypdf to 6.16.1 and re-ran the CI dependency audit command locally on 2026-09-20;
      no unexcepted advisories remain. Chroma server-only exceptions are reviewed below.
- [x] Version and user/developer/demo documentation updated for `0.1.0`.

## Intentionally pending

- [ ] Independent mentor review of `examples/eval/gold_ga4gh.yaml`.
- [ ] After review, revise labels if required and reconfirm or renegotiate the `0.90`
      engineering floor before treating any metric as independently validated.

## Deployment handoff

- [ ] Synchronize the repository's `render.yaml` Blueprint.
- [ ] Set `regbot-web.REGBOT_API_URL` to the deployed FastAPI public URL.
- [ ] Confirm `regbot-api /health` returns JSON rather than Streamlit HTML.
- [ ] Confirm `/api/meta/store` reports `retrieval_ready: true` and 8,078 manifest chunks.
- [ ] Confirm the Next.js public-user flow can run a consent check with at least one cited chunk.
- [ ] Decide whether administrator uploads must persist. If yes, attach a persistent disk and
      initialize `REGBOT_STORE` from the runtime start command because Render disks are not
      available during build or pre-deploy steps.

No commit, tag, push, merge, or release publication is performed by this checklist.

## Dependency advisory applicability (2026-09-20)

`pypdf==6.16.1` fixes PYSEC-2026-3910, PYSEC-2026-3911 and PYSEC-2026-3913.
The [XForm text-extraction advisory](https://github.com/py-pdf/pypdf/security/advisories/GHSA-763m-79hh-57f2)
is relevant to uploaded PDF processing, so it is fixed rather than excepted.

Chroma 1.5.9 remains affected by the following HTTP-server advisories. These are
applicability exceptions, not claims that the dependency is patched:

| Advisory | Vulnerable surface | Why it is not exposed here |
| --- | --- | --- |
| PYSEC-2026-311 | Separately exposed Chroma FastAPI server | Render starts `src.api.app`, not Chroma's server. |
| PYSEC-2026-3813 | Server tenant/database authorization | RegBot uses only an in-process `PersistentClient`; no tenant-management API is exposed. |
| PYSEC-2026-3814 | Server collection-update model configuration | RegBot computes and supplies embeddings; its API accepts no embedding-function/model configuration. |
| PYSEC-2026-3815 | Server cross-tenant collection authorization | No Chroma HTTP endpoint or remote tenant API is started or proxied. |

Sources: [upstream report](https://github.com/chroma-core/chroma/issues/7588),
[upstream fix PR](https://github.com/chroma-core/chroma/pull/7602), and
[model-configuration advisory](https://www.hiddenlayer.com/sai-security-advisory/2026-06-chromadb-5).
Reassess these exceptions before enabling Chroma's HTTP server, accepting caller-supplied
collection configuration, or changing the embedded-store architecture. The exact audit
command and exception IDs are maintained in `.github/workflows/ci.yml`.
