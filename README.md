### Google Summer of Code – Global Alliance for Genomics and Health ###

Overview
RegBot is a Global Alliance for Genomics and Health [Regulatory and Ethics Work Stream (REWS)](https://www.ga4gh.org/genomic-data-toolkit/regulatory-ethics-toolkit/) open-source tool in cross-border genomic data sharing. It complements the Alliance’s Regulatory & Ethics Toolkit by retrieving GA4GH and related policy provisions against researcher-supplied consent / data-use text and returning citation-grounded JSON for DPO, IRB, and DAC review—not compliance rulings or legal advice.

Documentation
- **`docs/DESIGN.md`** — architecture, data model, evaluation plan (GSoC design doc)
- **`docs/eval_results.md`** — measured retrieval benchmark: metrics, tuning runs, threats to validity
- **`docs/corpus_manifest.yaml`** — regulatory corpus inventory (23 documents; P0/P1 primary sources, P2 marked `summary`)
- **`examples/eval/gold_ga4gh.yaml`** — retrieval gold set (drafted; awaiting mentor review)
- **`examples/DEMO.md`** — local end-to-end demo

What works today
- **Ingest** policy PDFs or `.txt` files into a local **Chroma** store plus a JSON manifest. Chunks carry `source`, `page`, `category`, `document_id`, `jurisdiction`, `framework`, `content_type` (`primary` source text vs contributor `summary` — badged in the UI), and `section` (every heading the chunk spans) where the source is line-structured.
- **Hybrid retrieval**: exact cosine embedding search + **BM25**, fused by reciprocal rank (best-channel `max` by default; `REGBOT_FUSION=sum` for classic additive RRF). `jurisdiction` / `framework` / `category` filters scope the candidate search itself, not just the output. Ranking is deterministic — identical inputs give identical results across runs.
- **Compliance pass**: JSON-mode LLM via **[Ollama](https://ollama.com) by default** (e.g. `llama3`, configurable with `REGBOT_OLLAMA_MODEL`). Set `REGBOT_LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use OpenAI instead. If no LLM is reachable (or on API failure), a **keyword heuristic fallback** still returns grounded chunk ids.
- **Web UI** (recommended): FastAPI + Next.js in `frontend/` — see **Run the web UI** below.
- **Streamlit UI** (legacy): upload + paste flows (`src/streamlit_app.py`).
- **CLI**: `python -m src.main …` (see below).
- **Citation grounding (programmatic):** Each `recommendations[]` item must be `{ "text": "...", "evidence_chunk_ids": ["..."] }` with ids taken **only** from retrieved chunks; optional `citations[]` must also respect the same allow-list. Failed checks trigger **automatic rewrite requests** with the allow-list; optional **token-overlap** filtering on the LLM path (`REGBOT_MIN_TOKEN_OVERLAP`).
- **Reviewable evidence:** every recommendation carries `evidence[]` with the source document, page, a **verbatim quote** from the cited chunk, the jurisdiction, and a `governance_hint` naming the body that normally reviews that scope (DPO / IRB / DAC). Quotes are copied, never generated.
- **Fail-safe escalation:** when retrieval is thin, grounding fails, or the overlap filter drops everything, the report sets `needs_human_review` with a `review_reason` (`weak_retrieval` / `grounding_failed` / `low_overlap`) instead of presenting weak output as an answer.
- **Retrieval benchmark:** `benchmark` subcommand scores retrieval against a gold set (Recall@k / Precision@k / MRR) and can gate CI via `--min-recall`. Results: `docs/eval_results.md`.
- **PDF eval harness:** `eval` subcommand ingests a real GA4GH PDF and prints retrieval hits for built-in or custom queries (manual inspection; use `benchmark` for scored evaluation).

Quickstart (Development)
- Prerequisites: **Python 3.10–3.13** (the range `pyproject.toml` accepts; CI runs 3.11, which is the tested one). Python 3.14 is not supported yet for the full stack (native wheels for parts of the ML/Chroma toolchain often lag). Running the web UI also needs **Node 18+** for `frontend/`.
- Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

- Configure environment variables:
  - Export variables in your shell (recommended)
  - If you use a local `.env`, keep it private and do not commit it

- **LLM (default: local Ollama)**  
  Install [Ollama](https://ollama.com), run `ollama pull llama3` (or another tag you set in `REGBOT_OLLAMA_MODEL`), and keep the daemon running (`ollama serve` or `brew services start ollama` on macOS). No `OPENAI_API_KEY` is required for this path.

- **Embeddings (first ingest)**  
  The embedding model is downloaded from Hugging Face on first use. If downloads are slow or fail, try a longer timeout (`HF_HUB_DOWNLOAD_TIMEOUT`, seconds) or a mirror (`REGBOT_HF_ENDPOINT=https://hf-mirror.com` — sets `HF_ENDPOINT` for the Hub client).

- Ingest a policy file into `./data/regbot_store` (use `--reset` when reloading the same corpus):

```bash
python -m src.main ingest --path path/to/policy.pdf --reset
```

- Batch ingest from the corpus inventory (downloads go under `data/corpus/`; see `docs/corpus_manifest.yaml`):

```bash
python -m src.main ingest-manifest --dry-run
python -m src.main ingest-manifest --reset          # skips documents already ingested
python -m src.main ingest-manifest --reset --force  # re-ingest everything
python -m src.main ingest-manifest --tier P0 --reset
```

The store's Chroma vectors are git-ignored and regenerated by this command; the text
`manifest.json` is tracked as the BM25 corpus and citation-audit record.

- Rebuild the primary-source corpus from its publishers (EUR-Lex, GA4GH, Taiwan MOJ):

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
```

- Run the **web UI** (FastAPI + Next.js) from the repo root:

```bash
# Terminal 1 — API (repo root, venv active)
uvicorn src.api.app:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The Next.js dev server proxies `/api/*` and `/health` to the API on port 8000; set `REGBOT_API_URL` before `npm run dev` if the API is not on `http://127.0.0.1:8000`.

A fresh clone ships `manifest.json` but **not** the Chroma vectors (git-ignored), so run `ingest-manifest --reset` once before the UI can retrieve anything — the Corpus tab shows an empty store until you do.

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

Write a Markdown table, or fail below a recall threshold (CI gate):

```bash
python -m src.main benchmark --markdown docs/eval_results.md --min-recall 0.85
```

Run tests

```bash
python -m unittest discover -s tests -p "test*.py" -v
```

Environment Variables
- `REGBOT_LLM_PROVIDER`: **`ollama` (default)** — local LLM via Ollama’s OpenAI-compatible HTTP API (no OpenAI key). Set to **`openai`** to use OpenAI’s hosted API instead.
- `OPENAI_API_KEY`: Required only when `REGBOT_LLM_PROVIDER=openai`. Model: `REGBOT_LLM_MODEL` (default `gpt-4o-mini`).
- `REGBOT_OLLAMA_MODEL`: Tag known to Ollama (default `llama3`). Examples: `llama3`, `mistral`, `mistral:latest`.
- `REGBOT_OLLAMA_BASE_URL`: Ollama HTTP host only (default `http://127.0.0.1:11434`); `/v1` is appended automatically for the OpenAI-compatible routes.
- `REGBOT_OLLAMA_API_KEY`: Sent as the Bearer/API key to Ollama’s shim (default `ollama`; ignored by Ollama).
- `REGBOT_STORE`: On-disk store directory (default `./data/regbot_store`).
- `REGBOT_API_URL`: Read by the **Next.js dev server** (`frontend/next.config.ts`) to proxy `/api/*` and `/health` (default `http://127.0.0.1:8000`). Set it when the FastAPI process is on another host or port.
- `REGBOT_EMBEDDING_MODEL`: SentenceTransformers model id (default `sentence-transformers/all-MiniLM-L6-v2`).
- `HF_HUB_DOWNLOAD_TIMEOUT`: Hugging Face Hub download timeout in seconds (embedding model on first use). The app sets a higher default when unset; increase if you see read timeouts.
- `REGBOT_HF_ENDPOINT`: If set, copied to `HF_ENDPOINT` (e.g. `https://hf-mirror.com` where Hub mirrors are used).
- `REGBOT_MIN_TOKEN_OVERLAP`: On the LLM path, minimum **token recall** between each recommendation and cited chunk texts (default `0.06`). Set to `0` to disable dropping low-overlap rows.
- `REGBOT_SEMANTIC_CANDIDATES` / `REGBOT_BM25_CANDIDATES`: Candidate pool sizes feeding reciprocal rank fusion (defaults `12` / `48`). Lexical weighting was measured to beat balanced pools — see `docs/eval_results.md` §2.
- `REGBOT_FUSION`: `max` (default) takes each chunk's best channel; `sum` restores classic additive RRF. See `docs/eval_results.md` §4c.
- `REGBOT_MAX_CHUNKS_PER_PROVISION`: How many chunks of one provision (document + section) may occupy the result list (default `2`; `0` disables). A reviewer wants distinct applicable rules, not repeated fragments of one — see `docs/eval_results.md` §4g.
- `REGBOT_CHROMA_ANONYMIZED_TELEMETRY`: Set to `1` to enable Chroma client telemetry; default is off (`0`).
- `REGBOT_OPENAI_MAX_RETRIES`: Retries for the **OpenAI Python client** (used for both OpenAI API and Ollama’s compatible endpoint; default `3`).

Architecture (implemented vs planned)
- **Core:** Python 3, package under `src/regbot/` — ingestion, hybrid retrieval, fusion, grounding, evidence, evaluation, jurisdiction and text utilities.
- **Embeddings:** `sentence-transformers` + Hugging Face Hub (minimal file set; ONNX-heavy artifacts skipped where possible).
- **Vector store:** Chroma persistent files under `REGBOT_STORE/chroma` plus `manifest.json`, which holds chunk text and metadata for BM25 and citation audit.
- **Retrieval:** exact cosine ranking over the stored embeddings (loaded once from Chroma, ranked in process — the ANN index was approximate and made results irreproducible) + `rank-bm25`, fused by reciprocal rank. `jurisdiction` / `framework` / `category` filters restrict the candidate pool before the top-N cut.
- **LLM:** **Default:** Ollama (`llama3` or `REGBOT_OLLAMA_MODEL`) via OpenAI-compatible chat completions + JSON parsing. **Optional:** `REGBOT_LLM_PROVIDER=openai` with `OPENAI_API_KEY`. **Fallback:** keyword heuristic if OpenAI is selected without a key, or after LLM errors (e.g. Ollama not running).
- **API:** FastAPI (`src/api/app.py`) — corpus, chunk, ingest, check and chat endpoints behind `/api`.
- **UI:** Next.js in `frontend/` (recommended); Streamlit (`src/streamlit_app.py`) retained as the legacy single-process option.
- **Optional / roadmap:** LangChain or LlamaIndex adapters on top of the same stores (not required by the current code); richer offline evaluation (Ragas, human labels); a cross-encoder re-ranker over the fused pool (`docs/eval_results.md` §7).

