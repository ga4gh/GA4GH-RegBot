#!/usr/bin/env python3
"""Run ingest + check using the bundled sample files (no Streamlit).

Uses the same CLI as README/DEMO.md. Compliance analysis follows REGBOT_LLM_PROVIDER
(default: ollama + local llama3) or OpenAI when REGBOT_LLM_PROVIDER=openai and OPENAI_API_KEY is set.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    store = ROOT / "data" / "regbot_store"
    policy = ROOT / "examples" / "data" / "sample_ga4gh_policy_stub.txt"
    consent = ROOT / "examples" / "data" / "sample_consent_short.txt"
    py = sys.executable
    subprocess.check_call(
        [
            py,
            "-m",
            "src.main",
            "--store",
            str(store),
            "ingest",
            "--path",
            str(policy),
            "--reset",
        ],
        cwd=str(ROOT),
    )
    subprocess.check_call(
        [py, "-m", "src.main", "--store", str(store), "check", "--consent", str(consent)],
        cwd=str(ROOT),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
