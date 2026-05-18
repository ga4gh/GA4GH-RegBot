# Contributing to GA4GH-RegBot

## Environment

- Use **Python 3.10–3.12** (3.11 matches CI). Avoid 3.14 for the full ML/Chroma stack until wheels catch up.
- Create a venv and install runtime deps:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

- Optional dev tools (lint + pre-commit):

```bash
pip install -r requirements-dev.txt
pre-commit install
```

Run `pre-commit run --all-files` before pushing if you use the hook.

Unit tests do **not** require Ollama or `OPENAI_API_KEY`; the pipeline test forces the offline path.

## Tests

```bash
python -m unittest discover -s tests -p "test*.py" -v
```

## Lint

```bash
ruff check src tests
ruff format --check src tests
```

Auto-format:

```bash
ruff format src tests
```

## Type check (optional)

```bash
pip install -r requirements-dev.txt
python -m mypy -p src.regbot
```

This type-checks the `src.regbot` package (same as CI).

## Secrets and local data

- Do **not** commit `.env`, API keys, or your local vector store under `data/regbot_store/`.
- Keep PRs focused: one logical change per PR, update tests when behavior changes.

## Where to start

- See **Next steps** in `README.md` for suggested features (gold eval set, stricter JSON schema, ops hardening).
