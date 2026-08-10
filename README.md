# GA4GH-RegBot

## Overview

RegBot is an open-source tool for the Global Alliance for Genomics and Health [Regulatory and Ethics Work Stream (REWS)](https://www.ga4gh.org/genomic-data-toolkit/regulatory-ethics-toolkit/) and cross-border genomic data sharing. It complements the Alliance’s Regulatory & Ethics Toolkit by retrieving GA4GH and related policy provisions against researcher-supplied consent / data-use text and returning citation-grounded JSON for DPO, IRB, and DAC review—not compliance rulings or legal advice.

**Release status:** `0.1.0` release candidate. Implementation, corpus rebuild, the
41-query contributor-labelled benchmark, API/UI checks, and local Ollama validation are
complete. Independent mentor review of the gold set is intentionally still pending; the
scheduled benchmark remains informational until that review. The frontend dependency audit
is clean after the 2026-08-10 security update (see `docs/RELEASE_CHECKLIST.md`).

## Documentation

- **`docs/DESIGN.md`** — architecture, data model, evaluation plan (GSoC design doc)
- **`docs/eval_results.md`** — measured retrieval benchmark: metrics, tuning runs, threats to validity
- **`docs/corpus_manifest.yaml`** — regulatory corpus inventory (85 documents; `content_type` marks each as `primary`, `translation`, or `summary`)
- **`docs/CORPUS_SCOPE.md`** — inclusion criteria, regional coverage, exclusions, and the rule for reopening the corpus
- **`examples/eval/gold_ga4gh.yaml`** — retrieval gold set (drafted; awaiting mentor review)
- **`examples/DEMO.md`** — local end-to-end demo

## What works today

- **Ingest** policy PDFs or `.txt` files into a local **Chroma** store plus a JSON manifest. Chunks carry `source`, `page`, `category`, `document_id`, `jurisdiction`, `framework`, `content_type` (`primary` source text, non-authoritative/reference `translation`, or contributor `summary` — each badged in the UI), and `section` (every heading the chunk spans) where the source is line-structured.
- **Hybrid retrieval**: exact cosine embedding search + **BM25**, fused by reciprocal rank (best-channel `max` by default; `REGBOT_FUSION=sum` for classic additive RRF). `jurisdiction` / `framework` / `category` filters scope the candidate search itself, not just the output. Ranking is deterministic — identical inputs give identical results across runs.
- **Compliance pass**: JSON-mode LLM via **[Ollama](https://ollama.com) by default** (e.g. `llama3`, configurable with `REGBOT_OLLAMA_MODEL`). Set `REGBOT_LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use OpenAI instead. If no LLM is reachable, the keyword fallback keeps only recommendations with lexical support from a retrieved chunk and escalates unsupported rows for human review.
- **Web UI** (recommended): FastAPI + Next.js in `frontend/` — see **Run the web UI** below.
- **Streamlit UI** (legacy): upload + paste flows (`src/streamlit_app.py`).
- **CLI**: `python -m src.main …` (see below).
- **Citation grounding (programmatic):** Each `recommendations[]` item must be `{ "text": "...", "evidence_chunk_ids": ["..."] }` with ids taken **only** from retrieved chunks; optional `citations[]` must also respect the same allow-list. Failed LLM checks trigger **automatic rewrite requests** with the allow-list; both LLM and offline-fallback recommendations pass token-overlap filtering (`REGBOT_MIN_TOKEN_OVERLAP`).
- **Reviewable evidence:** every recommendation carries `evidence[]` with the source document, page, a **verbatim quote** from the cited chunk, the jurisdiction, and a `governance_hint` naming the body that normally reviews that scope (DPO / IRB / DAC). Quotes are copied, never generated.
- **Fail-safe escalation:** when retrieval is thin, grounding fails, or the overlap filter drops any recommendation, the report sets `needs_human_review` with a `review_reason` (`weak_retrieval` / `grounding_failed` / `low_overlap`) instead of presenting incomplete output as an answer.
- **Retrieval benchmark:** `benchmark` subcommand scores retrieval against a gold set (Recall@k / Precision@k / MRR) and can gate CI via `--min-recall`. Results: `docs/eval_results.md`.
- **PDF eval harness:** `eval` subcommand ingests a real GA4GH PDF and prints retrieval hits for built-in or custom queries (manual inspection; use `benchmark` for scored evaluation).

## Quickstart (development)

- Prerequisites: **Python 3.10–3.13** (the range `pyproject.toml` accepts; CI runs 3.11, which is the tested one). Python 3.14 is not supported yet for the full stack (native wheels for parts of the ML/Chroma toolchain often lag). Running the web UI also needs **Node 20.9+** for `frontend/` (CI uses Node 22).
- Confirm that the interpreter used to create the environment is in the supported range,
  then create the environment and install dependencies. The example names Python 3.11 to
  match CI; `python3.10`, `python3.12`, or `python3.13` are also valid:

```bash
python3.11 --version
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Also install test/lint/type-check dependencies when developing or verifying a release.
python -m pip install -r requirements-dev.txt
```

- Configure environment variables:
  - Export variables in your shell (recommended)
  - If you use a local `.env`, keep it private and do not commit it

- **Web login and roles (required for FastAPI / Next.js and Streamlit)**

  RegBot intentionally ships with no default password. The login page allows a public
  read-only user session by default; configure an administrator account for corpus
  management (account passwords require 12+ characters). A random in-memory session secret
  is generated automatically for local single-process use:

```bash
export REGBOT_ADMIN_USERNAME='admin'
export REGBOT_ADMIN_PASSWORD='replace-with-a-long-admin-password'
```

  Anyone can choose **Continue as public user** to browse, retrieve, run consent checks, and chat,
  but public-user sessions receive HTTP 403 for write operations and custom-store access. `admin`
  can upload/reset corpus content and select a custom store. Set
  `REGBOT_ALLOW_GUEST_VIEWER=0` to require named accounts for all access. Unauthenticated
  API requests receive HTTP 401. Sessions use a signed HttpOnly, SameSite=Lax cookie and
  expire after eight hours by default. Configure a stable 32+ character
  `REGBOT_SESSION_SECRET` for multi-worker deployments or sessions that must survive a
  server restart. For HTTPS deployment, also set `REGBOT_COOKIE_SECURE=1`.

- **LLM (default: local Ollama)**  
  Install [Ollama](https://ollama.com), run `ollama pull llama3` (or another tag you set in `REGBOT_OLLAMA_MODEL`), and keep the daemon running (`ollama serve` or `brew services start ollama` on macOS). No `OPENAI_API_KEY` is required for this path.

- **Embeddings (first ingest)**  
  The embedding model is downloaded from Hugging Face on first use. If downloads are slow or fail, try a longer timeout (`HF_HUB_DOWNLOAD_TIMEOUT`, seconds) or a mirror (`REGBOT_HF_ENDPOINT=https://hf-mirror.com` — sets `HF_ENDPOINT` for the Hub client).

- Ingest a policy file into `./data/regbot_store` (use `--reset` when reloading the same corpus):

```bash
python -m src.main ingest --path path/to/policy.pdf --reset
```

- Batch ingest from the corpus inventory (source files live under `data/corpus/`; see `docs/corpus_manifest.yaml`):

```bash
python -m src.main ingest-manifest --dry-run  # show documents absent from this local store
python -m src.main ingest-manifest            # add documents absent from this local store
python -m src.main ingest-manifest --reset    # clear and rebuild all 85 documents

# Build only P0 in a separate store; --store must precede the subcommand.
python -m src.main --store ./data/regbot_p0_store ingest-manifest --tier P0 --reset
```

The store's Chroma vectors are git-ignored and regenerated by this command; the text
`manifest.json` is tracked as the BM25 corpus and citation-audit record. The inventory's
`ingested_at` values are audit timestamps; incremental ingestion checks the active local
store instead of treating those timestamps as proof that vectors exist on this machine.

- Refresh the 83 reproducible source files from their publishers (GA4GH, EUR-Lex and
  regional legislative or government sites):

```bash
python tools/fetch_corpus.py --list     # show targets
python tools/fetch_corpus.py --check    # validate what is already on disk
python tools/fetch_corpus.py            # refresh everything
```

Each fetch is validated before it is written — a target declares required phrases and a
minimum length, so a publisher that serves a table of contents instead of the statute is
rejected rather than ingested.

- Check a consent / data-use text file:

```bash
python -m src.main check --consent path/to/consent.txt

# Jurisdiction filters are repeatable; this searches the union of SG and GA4GH.
python -m src.main check --consent path/to/consent.txt \
  --jurisdiction SG --jurisdiction GA4GH --top-k 8

# Framework filters are repeatable too and intersect with any jurisdiction scope.
python -m src.main check --consent path/to/consent.txt --framework GA4GH --top-k 8

python -m src.main status
```

- Run the **web UI** (FastAPI + Next.js) from the repo root:

```bash
# Terminal 1 — API (repo root, venv active)
uvicorn src.api.app:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm ci && npm run dev
```

Open [http://localhost:3000/login](http://localhost:3000/login). The Next.js dev server
proxies `/api/*` and `/health` to the API on port 8000; set `REGBOT_API_URL` before
`npm run dev` if the API is not on `http://127.0.0.1:8000`.

A fresh clone ships `manifest.json` but **not** the Chroma vectors (git-ignored), so run
`ingest-manifest --reset` once before the UI can retrieve anything. The Corpus tab lists
the inventory, but Browse and Check have no searchable chunks until this rebuild finishes.

- Run the legacy **Streamlit** UI:

```bash
python -m streamlit run src/streamlit_app.py
```

- End-to-end sample (synthetic policy + consent under `examples/`):

```bash
python examples/run_demo.py
```

Evaluate retrieval on a **real** GA4GH PDF (use `--reset` when reloading the same corpus):

```bash
python -m src.main eval --pdf path/to/ga4gh_policy.pdf --reset --top-k 8
```

Use your own query list (one line per query):

```bash
python -m src.main eval --pdf path/to/ga4gh_policy.pdf --reset --queries-file examples/eval/queries_ga4gh.txt
```

Optionally append a full compliance JSON report for a consent file:

```bash
python -m src.main eval --pdf path/to/ga4gh_policy.pdf --reset --consent path/to/consent.txt
```

Score retrieval against the gold set (Recall@k / Precision@k / MRR):

```bash
python -m src.main benchmark --gold examples/eval/gold_ga4gh.yaml
```

Write a Markdown table, or optionally fail below a recall threshold (CI gate):

```bash
python -m src.main benchmark --markdown /tmp/regbot-benchmark.md
python -m src.main benchmark --min-recall 0.70
```

The threshold applies to macro recall at the largest requested `--ks` value (default:
`recall@8`). Do not use it as a required release gate until the gold labels are independently
reviewed. Run `python -m src.main --help` or append `--help` to any subcommand for the full
CLI reference.

## Verification

```bash
python -m pytest -q
```

## Environment variables

- `REGBOT_LLM_PROVIDER`: **`ollama` (default)** — local LLM via Ollama’s OpenAI-compatible HTTP API (no OpenAI key). Set to **`openai`** to use OpenAI’s hosted API instead.
- `OPENAI_API_KEY`: Required only when `REGBOT_LLM_PROVIDER=openai`. Model: `REGBOT_LLM_MODEL` (default `gpt-4o-mini`).
- `REGBOT_OLLAMA_MODEL`: Tag known to Ollama (default `llama3`). Examples: `llama3`, `mistral`, `mistral:latest`.
- `REGBOT_OLLAMA_BASE_URL`: Ollama HTTP host only (default `http://127.0.0.1:11434`); `/v1` is appended automatically for the OpenAI-compatible routes.
- `REGBOT_OLLAMA_API_KEY`: Sent as the Bearer/API key to Ollama’s shim (default `ollama`; ignored by Ollama).
- `REGBOT_STORE`: On-disk store directory (default `./data/regbot_store`).
- `REGBOT_SESSION_SECRET`: Optional random session-signing secret of at least 32 characters. When unset, RegBot creates a per-process secret, so sessions end on restart and cannot span multiple workers. Configure it for production or multi-worker deployments; rotate it to invalidate all sessions.
- `REGBOT_ADMIN_USERNAME` / `REGBOT_ADMIN_PASSWORD`: Administrator credentials; username defaults to `admin` when its password is set, and the password must contain at least 12 characters.
- `REGBOT_VIEWER_USERNAME` / `REGBOT_VIEWER_PASSWORD`: Optional named read/review credentials. The environment-variable and internal role names retain `VIEWER` for backward compatibility; the UI calls this access level **user**. The username defaults to `viewer` when its password is set.
- `REGBOT_ALLOW_GUEST_VIEWER`: Allow the login page's account-free, read-only viewer entry (default `1`). Set to `0` to require a configured account for every user.
- `REGBOT_SESSION_HOURS`: Signed-session lifetime in hours (default `8`; clamped to `1`–`168`).
- `REGBOT_COOKIE_SECURE`: Set to `1` when serving over HTTPS so the login cookie is never sent over plaintext HTTP (default `0` for localhost development).
- `REGBOT_API_URL`: Read by the **Next.js dev server** (`frontend/next.config.ts`) to proxy `/api/*` and `/health` (default `http://127.0.0.1:8000`). Set it when the FastAPI process is on another host or port.
- `REGBOT_EMBEDDING_MODEL`: SentenceTransformers model id (default `sentence-transformers/all-MiniLM-L6-v2`).
- `HF_HUB_DOWNLOAD_TIMEOUT`: Hugging Face Hub download timeout in seconds (embedding model on first use). The app sets a higher default when unset; increase if you see read timeouts.
- `REGBOT_HF_ENDPOINT`: If set, copied to `HF_ENDPOINT` (e.g. `https://hf-mirror.com` where Hub mirrors are used).
- `HF_HUB_OFFLINE`: Set to `1` to skip Hub access and load the embedding model from the local cache.
- `REGBOT_MIN_TOKEN_OVERLAP`: Minimum **token recall** between each LLM or offline-fallback recommendation and its cited chunk texts (default `0.06`). Set to `0` to disable dropping low-overlap rows.
- `REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES`: Candidate pool sizes feeding reciprocal rank fusion (defaults `12` / `48`). Lexical weighting was measured to beat balanced pools — see `docs/eval_results.md` §2.
- `REGBOT_FUSION`: `max` (default) takes each chunk's best channel; `sum` restores classic additive RRF. See `docs/eval_results.md` §4c.
- `REGBOT_MAX_CHUNKS_PER_PROVISION`: How many chunks of one provision (document + section) may occupy the result list (default `2`; `0` disables). A reviewer wants distinct applicable rules, not repeated fragments of one — see `docs/eval_results.md` §4g.
- `REGBOT_CHROMA_ANONYMIZED_TELEMETRY`: Set to `1` to enable Chroma client telemetry; default is off (`0`).
- `REGBOT_OPENAI_MAX_RETRIES`: Retries for the **OpenAI Python client** (used for both OpenAI API and Ollama’s compatible endpoint; default `3`).

## Architecture (implemented vs planned)
- **Core:** Python 3, package under `src/regbot/` — ingestion, hybrid retrieval, fusion, grounding, evidence, evaluation, jurisdiction and text utilities.
- **Embeddings:** `sentence-transformers` + Hugging Face Hub (minimal file set; ONNX-heavy artifacts skipped where possible).
- **Vector store:** Chroma persistent files under `REGBOT_STORE/chroma` plus `manifest.json`, which holds chunk text and metadata for BM25 and citation audit.
- **Retrieval:** exact cosine ranking over the stored embeddings (loaded once from Chroma, ranked in process — the ANN index was approximate and made results irreproducible) + `rank-bm25`, fused by reciprocal rank. `jurisdiction` / `framework` / `category` filters restrict the candidate pool before the top-N cut.
- **LLM:** **Default:** Ollama (`llama3` or `REGBOT_OLLAMA_MODEL`) via OpenAI-compatible chat completions + JSON parsing. **Optional:** `REGBOT_LLM_PROVIDER=openai` with `OPENAI_API_KEY`. **Fallback:** keyword heuristic if OpenAI is selected without a key, or after LLM errors (e.g. Ollama not running).
- **API:** FastAPI (`src/api/app.py`) — signed-cookie authentication and role-protected corpus, chunk, ingest, check, and chat endpoints behind `/api`.
- **UI:** Next.js in `frontend/` (recommended); Streamlit (`src/streamlit_app.py`) retained as the legacy single-process option.
- **Access boundary:** Next.js/FastAPI and the legacy Streamlit UI enforce the same roles.
  API sessions use signed cookies; Streamlit uses its server-managed session. This does not
  replace operating-system permissions: a user with shell and filesystem access can still
  run the local CLI directly.
- **Optional / post-release:** LangChain or LlamaIndex adapters on top of the same stores; larger independently labelled evaluation sets. A cross-encoder is not part of `0.1.0` because the final benchmark does not show a provision-recall failure that justifies its model and latency cost.
