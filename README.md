GA4GH-RegBot: Compliance Assistant
Status: **MVP available** — ingest, hybrid retrieval, **local-first LLM** (Ollama / Llama 3 by default) or optional OpenAI, programmatic citation checks, CLI, Streamlit, and a small PDF eval harness. Ongoing work: real-corpus evaluation, stricter evidence objects, and contributor tooling.

Overview
RegBot is an LLM-powered tool designed to help researchers map their consent forms against GA4GH regulatory frameworks. It uses RAG (Retrieval-Augmented Generation) to flag compliance gaps automatically.

What works today
- **Ingest** policy PDFs or `.txt` files into a local **Chroma** store plus a JSON manifest (chunk ids, page hints, source metadata).
- **Hybrid retrieval**: embedding search + **BM25**, merged with reciprocal rank fusion.
- **Compliance pass**: JSON-mode LLM via **[Ollama](https://ollama.com) by default** (e.g. `llama3`, configurable with `REGBOT_OLLAMA_MODEL`). Set `REGBOT_LLM_PROVIDER=openai` and `OPENAI_API_KEY` to use OpenAI instead. If no LLM is reachable (or on API failure), a **keyword heuristic fallback** still returns grounded chunk ids.
- **Streamlit UI** for upload + paste flows (`src/streamlit_app.py`).
- **CLI**: `python -m src.main …` (see below).
- **Citation grounding (programmatic):** Each `recommendations[]` item must be `{ "text": "...", "evidence_chunk_ids": ["..."] }` with ids taken **only** from retrieved chunks; optional `citations[]` must also respect the same allow-list. Failed checks trigger **automatic rewrite requests** with the allow-list; optional **token-overlap** filtering on the LLM path (`REGBOT_MIN_TOKEN_OVERLAP`).
- **PDF eval harness:** `eval` subcommand ingests a real GA4GH PDF and prints retrieval hits for built-in or custom queries (for manual review / building a gold set later).

Quickstart (Development)
- Prerequisites: **Python 3.10–3.12** (CI uses 3.11). Python 3.14 is not supported yet for the full stack (native wheels for parts of the ML/Chroma toolchain often lag).
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

- Check a consent / data-use text file:

```bash
python -m src.main check --consent path/to/consent.txt
```

- Run the Streamlit UI from the repo root:

```bash
python -m streamlit run src/streamlit_app.py
```

- End-to-end sample (synthetic policy + consent under `examples/`):

```bash
python examples/run_demo.py
```

More detail: **`examples/DEMO.md`**.

Evaluate retrieval on a **real** GA4GH PDF (resets the store by default if you pass `--reset`):

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
- `REGBOT_EMBEDDING_MODEL`: SentenceTransformers model id (default `sentence-transformers/all-MiniLM-L6-v2`).
- `HF_HUB_DOWNLOAD_TIMEOUT`: Hugging Face Hub download timeout in seconds (embedding model on first use). The app sets a higher default when unset; increase if you see read timeouts.
- `REGBOT_HF_ENDPOINT`: If set, copied to `HF_ENDPOINT` (e.g. `https://hf-mirror.com` where Hub mirrors are used).
- `REGBOT_MIN_TOKEN_OVERLAP`: On the LLM path, minimum **token recall** between each recommendation and cited chunk texts (default `0.06`). Set to `0` to disable dropping low-overlap rows.
- `REGBOT_CHROMA_ANONYMIZED_TELEMETRY`: Set to `1` to enable Chroma client telemetry; default is off (`0`).
- `REGBOT_OPENAI_MAX_RETRIES`: Retries for the **OpenAI Python client** (used for both OpenAI API and Ollama’s compatible endpoint; default `3`).

Architecture (implemented vs planned)
- **Core:** Python 3, package under `src/regbot/` (ingest, hybrid retrieval, compliance, optional local embedding download helpers).
- **Embeddings:** `sentence-transformers` + Hugging Face Hub (minimal file set; ONNX-heavy artifacts skipped where possible).
- **Vector store:** Chroma persistent files under `REGBOT_STORE/chroma` plus `manifest.json` for BM25 text.
- **Retrieval:** cosine similarity in Chroma + `rank-bm25`, fused via reciprocal rank fusion; optional metadata category filter.
- **LLM:** **Default:** Ollama (`llama3` or `REGBOT_OLLAMA_MODEL`) via OpenAI-compatible chat completions + JSON parsing. **Optional:** `REGBOT_LLM_PROVIDER=openai` with `OPENAI_API_KEY`. **Fallback:** keyword heuristic if OpenAI is selected without a key, or after LLM errors (e.g. Ollama not running).
- **UI:** Streamlit (`src/streamlit_app.py`).
- **Optional / roadmap:** LangChain or LlamaIndex adapters on top of the same stores (not required by the current code); richer offline evaluation (Ragas, human labels); structured per-recommendation evidence (e.g. quotes).

Next steps (suggested priorities)
1. **Real GA4GH corpus**: ingest official PDFs, tune chunk size/overlap and hybrid fusion weights using `eval` + a small **gold query → chunk_id** list (manual or semi-automated).
2. **Richer evidence:** optional quoted spans, stricter refusal when retrieved excerpts are insufficient (grounding and token-overlap checks are already in place for the LLM path).
3. **Contributor experience**: **Done in-repo:** separate **Lint** workflow (Ruff check + format check), `CONTRIBUTING.md`, `.pre-commit-config.yaml`, `pyproject.toml`, `requirements-dev.txt`. **Still open:** optional CI `mypy`, broader type hints, Black-only rules if the team wants them.
4. **Operational hardening**: **Done in-repo:** Chroma telemetry off by default (`REGBOT_CHROMA_ANONYMIZED_TELEMETRY`), client `max_retries` (`REGBOT_OPENAI_MAX_RETRIES`), clear `ValueError` when a PDF yields no extractable text. **Next:** optional request timeouts, observability hooks.

Contributing
- See **`CONTRIBUTING.md`** for venv setup, **Ruff** lint/format, optional **pre-commit**, and tests.
- Open PRs against the upstream repo; keep changes scoped and tested (`python -m unittest discover -s tests -p "test*.py" -v`). Do not commit `.env`, API keys, or local `data/regbot_store/`.
