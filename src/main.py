from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

from src.regbot.compliance import analyze_compliance
from src.regbot.config import DEFAULT_COLLECTION
from src.regbot.eval_queries import DEFAULT_EVAL_QUERIES
from src.regbot.ingestion import ingest_policy_file
from src.regbot.retrieval import HybridRetriever
from src.regbot.study_type import detect_study_type


class RegBot:
    """
    GA4GH-oriented compliance assistant: ingest policy text, retrieve hybrid context,
    then analyze consent / data-use language with optional LLM JSON output
    (OpenAI API or local Ollama: Llama 3, Mistral, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        store_dir: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION,
        embedding_model: Optional[str] = None,
    ) -> None:
        load_dotenv()
        if api_key is None:
            self.api_key = os.getenv("OPENAI_API_KEY")
        else:
            # Treat "" as "no key" so callers/tests can force the offline fallback path.
            self.api_key = api_key or None
        self.store_dir = store_dir or os.getenv("REGBOT_STORE", "./data/regbot_store")
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self._retriever: Optional[HybridRetriever] = None

    def _retriever_instance(self) -> HybridRetriever:
        if self._retriever is None:
            kwargs: Dict[str, Any] = {
                "store_dir": self.store_dir,
                "collection_name": self.collection_name,
            }
            if self.embedding_model:
                kwargs["embedding_model_name"] = self.embedding_model
            self._retriever = HybridRetriever(**kwargs)
        return self._retriever

    def ingest_policy_documents(
        self,
        file_path: str,
        *,
        reset: bool = False,
        category: Optional[str] = None,
    ) -> bool:
        try:
            n = ingest_policy_file(
                file_path,
                self.store_dir,
                collection_name=self.collection_name,
                category=category,
                reset=reset,
            )
            return n >= 0
        except Exception as exc:  # noqa: BLE001 — surface failure to CLI/UI
            print(f"Ingest failed: {exc}", file=sys.stderr)
            return False

    def retrieve_relevant_clauses(
        self,
        user_query: str,
        *,
        top_k: int = 8,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        r = self._retriever_instance()
        if not r.is_ready():
            return []
        return r.retrieve(user_query, top_k=top_k, category=category)

    def compliance_report_and_chunks(
        self,
        user_consent_form: str,
        *,
        category: Optional[str] = None,
        top_k: int = 8,
    ) -> tuple[dict, List[Dict[str, Any]]]:
        """Same retrieval + compliance as check_compliance; also returns retrieved chunks."""
        study = detect_study_type(user_consent_form)
        chunks = self.retrieve_relevant_clauses(
            user_consent_form,
            top_k=top_k,
            category=category,
        )
        report = analyze_compliance(
            user_consent_form,
            chunks,
            study_type=study,
            api_key=self.api_key,
        )
        return report, chunks

    def check_compliance(
        self,
        user_consent_form: str,
        *,
        category: Optional[str] = None,
        top_k: int = 8,
    ) -> dict:
        report, _ = self.compliance_report_and_chunks(
            user_consent_form,
            category=category,
            top_k=top_k,
        )
        return report


def _cmd_ingest(args: argparse.Namespace) -> int:
    bot = RegBot(store_dir=args.store)
    ok = bot.ingest_policy_documents(
        args.path,
        reset=args.reset,
        category=args.category,
    )
    return 0 if ok else 1


def _cmd_check(args: argparse.Namespace) -> int:
    with open(args.consent, encoding="utf-8", errors="replace") as f:
        text = f.read()
    bot = RegBot(store_dir=args.store)
    report = bot.check_compliance(text, category=args.category, top_k=args.top_k)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    bot = RegBot(store_dir=args.store)
    r = bot._retriever_instance()
    ready = r.is_ready()
    print(json.dumps({"store": bot.store_dir, "retriever_ready": ready}, indent=2))
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    """
    Ingest a real GA4GH PDF (or text), then print retrieval diagnostics for benchmark queries.
    This is a lightweight harness for manual review; add your own gold labels over time.
    """
    bot = RegBot(store_dir=args.store)
    if not bot.ingest_policy_documents(
        args.pdf,
        reset=args.reset,
        category=args.category,
    ):
        return 1

    queries: List[str] = []
    if args.queries_file:
        with open(args.queries_file, encoding="utf-8", errors="replace") as f:
            queries = [ln.strip() for ln in f if ln.strip()]
    else:
        queries = list(DEFAULT_EVAL_QUERIES)

    rows: List[Dict[str, Any]] = []
    for q in queries:
        hits = bot.retrieve_relevant_clauses(q, top_k=args.top_k, category=args.category)
        rows.append(
            {
                "query": q,
                "hit_count": len(hits),
                "top_chunk_ids": [h["id"] for h in hits],
                "top_snippets": [(h.get("text") or "")[:240].replace("\n", " ") for h in hits[:3]],
            }
        )

    out: Dict[str, Any] = {"pdf": args.pdf, "store": args.store, "retrieval": rows}
    if args.consent:
        with open(args.consent, encoding="utf-8", errors="replace") as f:
            out["check_report"] = bot.check_compliance(
                f.read(),
                category=args.category,
                top_k=args.top_k,
            )
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "GA4GH-RegBot: ingest policy docs and check consent text. "
            "LLM defaults to local Ollama (see README); set REGBOT_LLM_PROVIDER=openai and "
            "OPENAI_API_KEY for OpenAI."
        ),
    )
    p.add_argument(
        "--store",
        default=os.getenv("REGBOT_STORE", "./data/regbot_store"),
        help="Directory for Chroma + manifest (default: ./data/regbot_store or REGBOT_STORE).",
    )
    sub = p.add_subparsers(dest="command")

    pi = sub.add_parser("ingest", help="Ingest a policy PDF or .txt into the local store.")
    pi.add_argument("--path", required=True, help="Path to PDF or text policy file.")
    pi.add_argument(
        "--reset",
        action="store_true",
        help="Clear this store before ingesting (recommended when re-loading the same corpus).",
    )
    pi.add_argument(
        "--category",
        default=None,
        help="Optional metadata category label (defaults to file stem).",
    )
    pi.set_defaults(func=_cmd_ingest)

    pc = sub.add_parser("check", help="Run compliance check against ingested policies.")
    pc.add_argument("--consent", required=True, help="Path to consent / data-use text file.")
    pc.add_argument(
        "--category",
        default=None,
        help="If set, only retrieve chunks with this category metadata.",
    )
    pc.add_argument("--top-k", type=int, default=8, dest="top_k")
    pc.set_defaults(func=_cmd_check)

    ps = sub.add_parser("status", help="Show whether a store exists and retriever can load.")
    ps.set_defaults(func=_cmd_status)

    pe = sub.add_parser(
        "eval",
        help="Ingest a PDF/txt and run default (or custom) retrieval queries for evaluation.",
    )
    pe.add_argument("--pdf", required=True, help="Path to a GA4GH policy PDF or text export.")
    pe.add_argument(
        "--reset",
        action="store_true",
        help="Clear the store before ingesting this PDF.",
    )
    pe.add_argument("--category", default=None, help="Optional metadata category filter.")
    pe.add_argument(
        "--queries-file",
        default=None,
        help="One query per line; if omitted, built-in GA4GH-oriented probes are used.",
    )
    pe.add_argument(
        "--consent",
        default=None,
        help="Optional consent file path; if set, runs check_compliance and includes the report.",
    )
    pe.add_argument("--top-k", type=int, default=8, dest="top_k")
    pe.set_defaults(func=_cmd_eval)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
