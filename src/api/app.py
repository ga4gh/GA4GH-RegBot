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
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth import (
    SESSION_COOKIE,
    AuthUser,
    auth_settings,
    authenticate,
    create_session_token,
    guest_viewer,
    require_admin,
    require_user,
)
from src.api.errors import guided_error_detail, guided_http_exception
from src.api.schemas import (
    AuthUserResponse,
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
    LoginRequest,
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


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = sorted(
        {
            ".".join(str(part) for part in error.get("loc", [])[1:])
            for error in exc.errors()
            if error.get("loc")
        }
    )
    field_text = ", ".join(field for field in fields if field) or "request fields"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "detail": {
                "code": "INVALID_REQUEST",
                "message": f"Some submitted values are invalid: {field_text}.",
                "action": "Correct the highlighted input values and submit the request again.",
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_backend_error(_request: Request, exc: Exception) -> JSONResponse:
    status_code, detail = guided_error_detail(exc, operation="handling an API request")
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _resolve_store(store_dir: Optional[str], user: Optional[AuthUser] = None) -> str:
    resolved = store_dir.strip() if store_dir and store_dir.strip() else _DEFAULT_STORE
    if user and user.role != "admin":
        requested_path = Path(resolved).expanduser().resolve()
        default_path = Path(_DEFAULT_STORE).expanduser().resolve()
        if requested_path != default_path:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators may select a custom store directory.",
            )
    return resolved


def _bot(store_dir: Optional[str] = None, user: Optional[AuthUser] = None) -> RegBot:
    return RegBot(store_dir=_resolve_store(store_dir, user))


def _require_retrieval_ready(bot: RegBot) -> None:
    if bot.is_retrieval_ready():
        return
    manifest_chunk_count = len(read_manifest(bot.store_dir))
    message = (
        "The corpus manifest is available, but the retrieval index is not ready."
        if manifest_chunk_count
        else "The corpus manifest and retrieval index are not ready."
    )
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "CORPUS_STORE_UNAVAILABLE",
            "message": message,
            "action": (
                "Ask an administrator to rebuild the vector index with "
                "`python -m src.main ingest-manifest --reset`."
            ),
        },
    )


def _corpus_documents() -> List[Dict[str, Any]]:
    data = load_corpus_manifest(_CORPUS_MANIFEST_PATH)
    return list(data.get("documents") or [])


def _chunk_out(rec: Dict[str, Any]) -> ChunkOut:
    meta = dict(rec.get("metadata") or {})
    # Old stores may predate portable manifests. Never expose a server filesystem path.
    meta.pop("source_path", None)
    tags = sorted(chunk_jurisdiction_tags(meta))
    if tags and "jurisdiction" not in meta:
        meta["jurisdiction"] = tags
    return ChunkOut(
        id=str(rec.get("id") or ""),
        text=str(rec.get("text") or ""),
        metadata=meta,
    )


def _trusted_chunks(store_dir: str, submitted: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Resolve client-selected chunk ids against the active store's canonical records."""
    requested_ids = [str(chunk.get("id") or "").strip() for chunk in submitted]
    if not all(requested_ids):
        raise HTTPException(status_code=400, detail="Every submitted chunk must have an id.")

    try:
        stored = read_manifest(store_dir)
    except Exception as exc:
        raise guided_http_exception(exc, operation="loading submitted policy evidence") from exc
    by_id = {str(chunk.get("id") or ""): chunk for chunk in stored}
    unknown = sorted({chunk_id for chunk_id in requested_ids if chunk_id not in by_id})
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="Submitted evidence contains chunk ids that are not in the active store.",
        )

    # Preserve the client's evidence order, but do not let duplicate ids inflate context.
    seen = set()
    trusted: List[Dict[str, Any]] = []
    for chunk_id in requested_ids:
        if chunk_id not in seen:
            trusted.append(by_id[chunk_id])
            seen.add(chunk_id)
    return trusted


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


def _set_session_cookie(response: Response, user: AuthUser) -> None:
    settings = auth_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user),
        max_age=settings.session_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@app.post("/api/auth/guest", response_model=AuthUserResponse)
def guest_login(response: Response) -> AuthUserResponse:
    user = guest_viewer()
    _set_session_cookie(response, user)
    return AuthUserResponse(username=user.username, role=user.role)


@app.post("/api/auth/login", response_model=AuthUserResponse)
def login(body: LoginRequest, response: Response) -> AuthUserResponse:
    user = authenticate(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    _set_session_cookie(response, user)
    return AuthUserResponse(username=user.username, role=user.role)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = auth_settings()
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"


@app.get("/api/auth/me", response_model=AuthUserResponse)
def current_user(
    response: Response,
    user: AuthUser = Depends(require_user),
) -> AuthUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthUserResponse(username=user.username, role=user.role)


@app.get("/api/meta/jurisdictions", response_model=List[JurisdictionOption])
def list_jurisdictions(_user: AuthUser = Depends(require_user)) -> List[JurisdictionOption]:
    return [
        JurisdictionOption(code=code, label=label) for code, label in jurisdiction_options_for_ui()
    ]


@app.get("/api/meta/store", response_model=StoreMetaResponse)
def store_meta(
    store_dir: Optional[str] = Query(default=None),
    user: AuthUser = Depends(require_user),
) -> StoreMetaResponse:
    resolved = _resolve_store(store_dir, user)
    try:
        store_status = _bot(resolved, user).store_status()
        corpus_document_count = len(_corpus_documents())
    except Exception as exc:
        raise guided_http_exception(exc, operation="loading corpus metadata") from exc
    return StoreMetaResponse(
        store_dir=resolved,
        jurisdictions=store_status["jurisdictions"],
        corpus_document_count=corpus_document_count,
        manifest_chunk_count=store_status["manifest_chunk_count"],
        retrieval_ready=store_status["retrieval_ready"],
        llm_hint=_LLM_HINT,
    )


@app.get("/api/corpus", response_model=CorpusResponse)
def get_corpus(
    region: Optional[str] = Query(default=None, description="Jurisdiction filter code"),
    _user: AuthUser = Depends(require_user),
) -> CorpusResponse:
    try:
        docs = _corpus_documents()
    except Exception as exc:
        raise guided_http_exception(exc, operation="loading the corpus inventory") from exc
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
    user: AuthUser = Depends(require_user),
) -> ChunksResponse:
    if region.upper() not in JURISDICTION_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown jurisdiction: {region}")
    resolved = _resolve_store(store_dir, user)
    try:
        chunks = read_manifest(resolved)
    except Exception as exc:
        raise guided_http_exception(exc, operation="opening the policy corpus") from exc
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
    user: AuthUser = Depends(require_admin),
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
        bot = _bot(store_dir, user)
        ok = bot.ingest_policy_documents(
            tmp_path,
            reset=reset,
            category=category.strip() or None,
            jurisdiction=jurisdiction.upper(),
            raise_on_error=True,
        )
        if ok:
            return IngestResponse(
                ok=True,
                jurisdiction=jurisdiction.upper(),
                message=f"Ingest finished ({jurisdiction.upper()}).",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INGEST_FAILED",
                "message": "The document was not added to the corpus.",
                "action": "Retry once. If the problem continues, ask the server operator to check the API logs.",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise guided_http_exception(exc, operation="ingesting an uploaded policy document") from exc
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.post("/api/check", response_model=CheckResponse)
def check_consent(
    body: CheckRequest,
    user: AuthUser = Depends(require_user),
) -> CheckResponse:
    if not body.consent_text.strip():
        raise HTTPException(status_code=400, detail="consent_text is required.")
    bot = _bot(body.store_dir, user)
    _require_retrieval_ready(bot)
    jur_filter = parse_jurisdiction_filter(body.jurisdictions)
    try:
        report, chunks = bot.compliance_report_and_chunks(
            body.consent_text,
            category=body.category.strip() or None if body.category else None,
            jurisdiction=jur_filter,
            top_k=body.top_k,
        )
    except Exception as exc:
        raise guided_http_exception(exc, operation="checking consent text") from exc
    scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
    return CheckResponse(
        report=report,
        chunks=[_chunk_out(c) for c in chunks],
        scope=scope,
        chunk_count=len(chunks),
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat_followup(
    body: ChatRequest,
    user: AuthUser = Depends(require_user),
) -> ChatResponse:
    if not body.messages:
        return ChatResponse(reply="Please enter a question.")

    user_query = ""
    for m in reversed(body.messages):
        if m.role == "user" and m.content.strip():
            user_query = m.content.strip()
            break
    if not user_query:
        return ChatResponse(reply="Please enter a question.")

    bot = _bot(body.store_dir, user)
    jur_filter = parse_jurisdiction_filter(body.jurisdictions)
    chunks: List[Dict[str, Any]] = (
        _trusted_chunks(bot.store_dir, body.chunks) if body.chunks else []
    )
    if not chunks:
        _require_retrieval_ready(bot)
        try:
            chunks = bot.retrieve_relevant_clauses(
                user_query,
                top_k=body.top_k,
                category=body.category.strip() if body.category else None,
                jurisdiction=jur_filter,
            )
        except Exception as exc:
            raise guided_http_exception(
                exc, operation="retrieving policy evidence for chat"
            ) from exc

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
        raise guided_http_exception(exc, operation="generating a policy answer") from exc

    scope = ", ".join(jur_filter) if jur_filter else "all jurisdictions"
    return ChatResponse(
        reply=reply,
        chunks=[_chunk_out(c) for c in chunks],
        scope=scope,
    )
