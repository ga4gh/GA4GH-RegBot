# Demo (local)

From the repository root, with a virtualenv activated and dependencies installed (`pip install -r requirements.txt`). For the compliance step, **embeddings** download on first ingest (Hugging Face); **default LLM is local Ollama** (`llama3` unless `REGBOT_OLLAMA_MODEL` is set)—install [Ollama](https://ollama.com), run `ollama pull llama3`, and keep the daemon running.

1. Ingest the bundled synthetic policy text (resets the local store):

```bash
python -m src.main --store ./data/regbot_store ingest --path examples/data/sample_ga4gh_policy_stub.txt --reset
```

2. Run a check against the sample consent:

```bash
python -m src.main --store ./data/regbot_store check --consent examples/data/sample_consent_short.txt
```

3. Or run both steps via the helper script (same as 1+2):

```bash
python examples/run_demo.py
```

4. Optional UI:

```bash
python -m streamlit run src/streamlit_app.py
```

**LLM behavior:** With **Ollama** running and default settings (`REGBOT_LLM_PROVIDER` defaults to `ollama`), you get JSON compliance output from the local model without `OPENAI_API_KEY`. To use **OpenAI** instead: `export REGBOT_LLM_PROVIDER=openai` and set `OPENAI_API_KEY`; optional `REGBOT_LLM_MODEL` (default `gpt-4o-mini`). If no LLM is reachable, the tool still retrieves policy chunks and uses a **keyword-style fallback** with grounded chunk ids.
