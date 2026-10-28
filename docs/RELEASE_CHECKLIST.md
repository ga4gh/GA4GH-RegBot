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
- [x] Updated pypdf to 6.19.0 on 2026-10-16 (PYSEC-2026-4153 to -4160); made the PDF
      extraction mode a property of the extracted text rather than of the pypdf release,
      rebuilt the store (8,053 chunks) and re-ran the benchmark with identical gate figures.
- [x] Re-audited dependencies on 2026-10-28: Pillow 13.0.0 (37 advisories against 12.3.0),
      which needs Streamlit 1.66.1 and therefore Python >= 3.11; Next.js 16.4.3 and
      `npm audit fix` for the frontend, leaving three low-severity `deepmerge` findings inside
      the shadcn CLI. pypdf is held at 6.19.0 under the exceptions reviewed below.
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

## Dependency advisory applicability (2026-10-28)

`pypdf==6.19.0` fixes PYSEC-2026-4153 to PYSEC-2026-4160 on top of the 6.16.1 fixes
(PYSEC-2026-3910, PYSEC-2026-3911, PYSEC-2026-3913).
The [XForm text-extraction advisory](https://github.com/py-pdf/pypdf/security/advisories/GHSA-763m-79hh-57f2)
is relevant to uploaded PDF processing, so it is fixed rather than excepted.

Eleven later pypdf advisories, fixed between 6.20.0 and 6.21.2, are held as applicability
exceptions because every release that fixes them breaks corpus extraction. From 6.20.0 the
layout extractor no longer restores word spacing in the Singapore statutes: under 6.21.2 the
Human Biomedical Research Act falls from 23,061 to 10,993 words with 1,307 run-on tokens of
24+ letters, and the Personal Data Protection Act from 31,059 to 13,671. Plain extraction was
already collapsed for these files, so no extraction mode recovers them; 6.21.3 and 6.21.4
behave the same.

| Advisory | Fixed in | Trigger | Why it is not exposed here |
| --- | --- | --- | --- |
| GHSA-39mj-jf6j-2qj3 | 6.20.0 | File truncated inside the xref table | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-7mh2-4gg2-979f | 6.20.0 | Stream with many or data-amplifying filters | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-qfv9-64jg-mh7p | 6.20.1 | `PdfWriter.find_outline_item` | RegBot never uses `PdfWriter`. |
| GHSA-9mx8-4j7g-633p | 6.20.1 | Removing an object from a tree (e.g. an outline item) | RegBot only reads; it never edits outlines or trees. |
| GHSA-cgf9-327m-v77c | 6.21.0 | Content stream with many small operations | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-f54x-cmq8-qg57 | 6.21.0 | Arrays or dictionaries with many elements | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-6vvc-x485-93v7 | 6.21.0 | Retrieving form fields | RegBot never reads form fields. |
| GHSA-5hx5-vpf9-5wcv | 6.21.1 | Loading an image that claims `/DCTDecode` | RegBot extracts text only and never loads page images. |
| GHSA-6c7f-9265-g8fw | 6.21.2 | Repeated references to one missing object | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-jr96-gvgh-j3r4 | 6.21.2 | Repeated malformed cross-reference streams | Needs an attacker-supplied PDF; PDF input is administrator-only. |
| GHSA-gmh7-3g9r-mjh5 | 6.21.2 | Wrong upper limits in the xref table | Needs an attacker-supplied PDF; PDF input is administrator-only. |

RegBot opens PDFs only through `PdfReader(...).pages[i].extract_text()`. Corpus PDFs come from
the manifest's official sources; the other PDF inputs, `/api/ingest` and the Streamlit ingest
tab, require the administrator role. Upgrade pypdf and drop these exceptions once the loader
restores word spacing under 6.20+, or immediately if PDF upload is opened to non-administrators.

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
