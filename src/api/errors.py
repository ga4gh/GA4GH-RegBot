"""Safe, actionable API errors for failures raised by backend dependencies."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ErrorGuide:
    status_code: int
    code: str
    message: str
    action: str


def _classify_exception(exc: Exception) -> ErrorGuide:
    """Map implementation failures to stable, user-facing recovery guidance."""
    text = str(exc).lower()

    if isinstance(exc, PermissionError) or "permission denied" in text:
        return ErrorGuide(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STORE_PERMISSION_DENIED",
            "RegBot cannot read or write its corpus store.",
            "Ask the server operator to check the REGBOT_STORE path and its file permissions, then retry.",
        )

    if (
        "hugging face" in text
        or "sentence-transform" in text
        or "embedding model" in text
        or "hf_hub" in text
    ):
        return ErrorGuide(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "EMBEDDING_MODEL_UNAVAILABLE",
            "The embedding model required for policy retrieval is unavailable.",
            "For the first run, connect the server to Hugging Face or configure REGBOT_HF_ENDPOINT. "
            "For offline use, cache the model first or point REGBOT_EMBEDDING_MODEL to a local directory.",
        )

    if (
        "no extractable text" in text
        or "contains no text" in text
        or "no chunk carries" in text
        or "needs ocr" in text
    ):
        return ErrorGuide(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "DOCUMENT_NOT_CITABLE",
            "The uploaded document does not contain enough extractable policy text.",
            "Upload a text-based PDF or .txt file. If the PDF is a scan, run OCR and upload the OCR version.",
        )

    if isinstance(exc, FileNotFoundError) or "no such file or directory" in text:
        return ErrorGuide(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CORPUS_FILE_MISSING",
            "A required corpus or store file is missing on the server.",
            "Ask an administrator to run `python -m src.main ingest-manifest --reset` from the repository root.",
        )

    if (
        "chromadb" in text
        or "chroma" in text
        or "manifest.json" in text
        or "collection" in text
        or "sqlite" in text
    ):
        return ErrorGuide(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CORPUS_STORE_UNAVAILABLE",
            "The policy corpus store could not be opened.",
            "Ask an administrator to verify REGBOT_STORE. If the store is incomplete, rebuild it with "
            "`python -m src.main ingest-manifest --reset`.",
        )

    if (
        "ollama" in text
        or "openai" in text
        or "api key" in text
        or "rate limit" in text
        or "llm" in text
    ):
        return ErrorGuide(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LLM_UNAVAILABLE",
            "The language model service is unavailable or incorrectly configured.",
            "For local mode, start Ollama and ensure REGBOT_OLLAMA_MODEL is installed. For OpenAI, "
            "set REGBOT_LLM_PROVIDER=openai and provide a valid OPENAI_API_KEY.",
        )

    return ErrorGuide(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "RegBot could not complete this request because of an unexpected server error.",
        "Retry once. If the problem continues, give the error reference to the server operator so they can check the logs.",
    )


def guided_error_detail(exc: Exception, *, operation: str) -> tuple[int, dict[str, Any]]:
    """Log the full failure and return a safe explanation suitable for an API response."""
    guide = _classify_exception(exc)
    reference = secrets.token_hex(4)
    logger.exception("RegBot backend failure [%s] while %s", reference, operation, exc_info=exc)
    return guide.status_code, {
        "code": guide.code,
        "message": guide.message,
        "action": guide.action,
        "reference": reference,
    }


def guided_http_exception(exc: Exception, *, operation: str) -> HTTPException:
    status_code, detail = guided_error_detail(exc, operation=operation)
    return HTTPException(status_code=status_code, detail=detail)
