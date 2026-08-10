# Contributing to GA4GH-RegBot

## Environment

- Use **Python 3.10–3.13** (the range `pyproject.toml` accepts; 3.11 matches CI). Avoid 3.14 for the full ML/Chroma stack until wheels catch up.
- Working on `frontend/` also needs **Node 20.9+** (CI uses 22).
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
python -m pytest -q
```

## Lint

```bash
ruff check src tests tools
ruff format --check src tests tools
```

Auto-format:

```bash
ruff format src tests tools
```

## Type check (optional)

```bash
pip install -r requirements-dev.txt
python -m mypy -p src.regbot
```

This type-checks the `src.regbot` package (same as CI).

## Frontend (`frontend/`)

Run all three before pushing a change to the Next.js UI — CI runs the same set on any
PR that touches `frontend/`:

```bash
npm --prefix frontend run lint
npx --prefix frontend tsc -p frontend/tsconfig.json --noEmit
npm --prefix frontend run build
```

`npm run lint` enforces the React hook rules, including `set-state-in-effect`: an effect
body may not update state synchronously. Mirroring a prop into state, or starting a fetch
with `setLoading(true)`, will fail here — derive from the prop instead, or raise the flag
in the event handler that starts the fetch.

## Secrets and local data

- Do **not** commit `.env`, API keys, or your local vector store under `data/regbot_store/`.
- Keep PRs focused: one logical change per PR, update tests when behavior changes.

## Where to start

- See `docs/eval_results.md` for measured limitations and `docs/RELEASE_CHECKLIST.md` for
  the remaining release blocker: independent review of the contributor-labelled gold set.
