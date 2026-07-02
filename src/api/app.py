from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    CheckRequest,
    CheckResponse,
    ChunkOut,
    ChunksResponse,
    CorpusDocument,
    CorpusResponse,
    IngestResponse,
    JurisdictionOption,
    StoreMetaResponse,
)
from src.main import RegBot
from src.regbot.compliance import chat_followup_policy_qa
from src.regbot.corpus_manifest import load_corpus_manifest
from src.regbot.ingestion import read_manifest
from src.regbot.jurisdiction import (
    JURISDICTION_CODES,
    chunk_jurisdiction_tags,
    jurisdiction_matches,
    jurisdiction_options_for_ui,
    parse_jurisdiction_filter,
)

load_dotenv()

_CORPUS_MANIFEST_PATH = str(_ROOT / "docs" / "corpus_manifest.yaml")
_DEFAULT_STORE = os.getenv("REGBOT_STORE", "./data/regbot_store")
_LLM_HINT = (
    "Default: local Ollama (REGBOT_OLLAMA_MODEL, e.g. llama3). "
    "For OpenAI, set REGBOT_LLM_PROVIDER=openai and OPENAI_API_KEY. "
    "If the LLM is unreachable, a heuristic fallback runs."
)

app = FastAPI(
    title="GA4GH-RegBot API",
    description="REST API for policy ingest, retrieval, and regulatory navigation checks.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_store(store_dir: Optional[str]) -> str:
    return store_dir.strip() if store_dir and store_dir.strip() else _DEFAULT_STORE


def _bot(store_dir: Optional[str] = None) -> RegBot:
    return RegBot(store_dir=_resolve_store(store_dir))


def _corpus_documents() -> List[Dict[str, Any]]:
    try:
        data = load_corpus_manifest(_CORPUS_MANIFEST_PATH)
        return list(data.get("documents") or [])
    except Exception:
        return []


def _chunk_out(rec: Dict[str, Any]) -> ChunkOut:
    meta = dict(rec.get("metadata") or {})
    tags = sorted(chunk_jurisdiction_tags(meta))
    if tags and "jurisdiction" not in meta:
        meta["jurisdiction"] = tags
    return ChunkOut(
        id=str(rec.get("id") or ""),
        text=str(rec.get("text") or ""),
        metadata=meta,
    )


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta/jurisdictions", response_model=List[JurisdictionOption])
def list_jurisdictions() -> List[JurisdictionOption]:
    return [
        JurisdictionOption(code=code, label=label) for code, label in jurisdiction_options_for_ui()
    ]


@app.get("/api/meta/store", response_model=StoreMetaResponse)
def store_meta(store_dir: Optional[str] = Query(default=None)) -> StoreMetaResponse:
    resolved = _resolve_store(store_dir)
    try:
        jurisdictions = _bot(resolved).list_store_jurisdictions()
    except Exception:
        jurisdictions = []
    return StoreMetaResponse(
        store_dir=resolved,
        jurisdictions=jurisdictions,
        corpus_document_count=len(_corpus_documents()),
        llm_hint=_LLM_HINT,
    )


@app.get("/api/corpus", response_model=CorpusResponse)
def get_corpus(
    region: Optional[str] = Query(default=None, description="Jurisdiction filter code"),
) -> CorpusResponse:
    docs = _corpus_documents()
    if region and region.upper() != "ALL":
        want = region.upper()
        docs = [d for d in docs if want in {str(j).upper() for j in (d.get("jurisdiction") or [])}]
    out: List[CorpusDocument] = []
    for doc in docs:
        out.append(
            CorpusDocument(
                document_id=str(doc.get("document_id") or ""),
                title=str(doc.get("title") or doc.get("document_id") or "Untitled"),
                tier=str(doc.get("tier") or "P2"),
                jurisdiction=[str(j) for j in (doc.get("jurisdiction") or [])],
                ingested_at=str(doc.get("ingested_at") or "") or None,
                source_url=str(doc.get("source_url") or "").strip() or None,
            )
        )
    return CorpusResponse(documents=out, total=len(out))


@app.get("/api/chunks", response_model=ChunksResponse)
def get_chunks(
    region: str = Query(..., description="Jurisdiction code"),
    limit: int = Query(default=25, ge=1, le=80),
    store_dir: Optional[str] = Query(default=None),
) -> ChunksResponse:
    if region.upper() not in JURISDICTION_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown jurisdiction: {region}")
    resolved = _resolve_store(store_dir)
    try:
        chunks = read_manifest(resolved)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    selected = parse_jurisdiction_filter([region])
    matched = [rec for rec in chunks if jurisdiction_matches(rec.get("metadata"), selected)]
    sliced = matched[:limit]
    return ChunksResponse(
        region=region.upper(),
        chunks=[_chunk_out(rec) for rec in sliced],
        total=len(matched),
    )


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_policy(
    file: UploadFile = File(...),
    reset: bool = Form(default=False),
    category: str = Form(default=""),
    jurisdiction: str = Form(default="GA4GH"),
    store_dir: Optional[str] = Form(default=None),
) -> IngestResponse:
    if jurisdiction.upper() not in JURISDICTION_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown jurisdiction: {jurisdiction}")

    suffix = Path(file.filename or "upload.txt").suffix or ".txt"
    if suffix.lower() not in {".pdf", ".txt"}:
        raise HTTPException(status_code=400, detail="Only PDF and .txt files are supported.")

    content = await file.read()
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        bot = _bot(store_dir)
        ok = bot.ingest_policy_documents(
            tmp_path,
            reset=reset,
            category=category.strip() or None,
            jurisdiction=jurisdiction.upper(),
        )
        if ok:
            return IngestResponse(
                ok=True,
                jurisdiction=jurisdiction.upper(),
                message=f"Ingest finished ({jurisdiction.upper()}).",
            )
        return IngestResponse(
            ok=False,
            jurisdiction=jurisdiction.upper(),
            message="Ingest reported a problem (see server logs).",
        )
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.post("/api/check", response_model=CheckResponse)
def check_consent(body: CheckRequest) -> CheckResponse:
    if not body.consent_text.strip():
        raise HTTPException(status_code=400, detail="consent_text is required.")
    bot = _bot(body.store_dir)
    jur_filter = parse_jurisdiction_filter(body.jurisdictions)
    try:
        report, chunks = bot.compliance_report_and_chunks(
            body.consent_text,
            category=body.category.strip() or None if body.category else None,
            jurisdiction=jur_filter,
            top_k=body.top_k,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
    return CheckResponse(
        report=report,
        chunks=[_chunk_out(c) for c in chunks],
        scope=scope,
        chunk_count=len(chunks),
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat_followup(body: ChatRequest) -> ChatResponse:
    if not body.messages:
        return ChatResponse(reply="Please enter a question.")

    user_query = ""
    for m in reversed(body.messages):
        if m.role == "user" and m.content.strip():
            user_query = m.content.strip()
            break
    if not user_query:
        return ChatResponse(reply="Please enter a question.")

    bot = _bot(body.store_dir)
    jur_filter = parse_jurisdiction_filter(body.jurisdictions)
    chunks: List[Dict[str, Any]] = list(body.chunks) if body.chunks else []
    if not chunks:
        try:
            chunks = bot.retrieve_relevant_clauses(
                user_query,
                top_k=body.top_k,
                category=body.category.strip() if body.category else None,
                jurisdiction=jur_filter,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not chunks:
        scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
        return ChatResponse(
            reply=(
                "No policy chunks matched your question and jurisdiction filter. "
                "Ingest the corpus (or try another jurisdiction)."
            ),
            scope=scope,
        )

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        reply = chat_followup_policy_qa(
            chunks,
            body.consent_text,
            messages,
            api_key=bot.api_key,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
    return ChatResponse(
        reply=reply,
        chunks=[_chunk_out(c) for c in chunks],
        scope=scope,
    )
