from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class AuthUserResponse(BaseModel):
    username: str
    role: Literal["admin", "viewer"]


class JurisdictionOption(BaseModel):
    code: str
    label: str


class CorpusDocument(BaseModel):
    document_id: str
    title: str
    tier: str
    jurisdiction: List[str]
    ingested_at: Optional[str] = None
    source_url: Optional[str] = None


class CorpusResponse(BaseModel):
    documents: List[CorpusDocument]
    total: int


class ChunkMeta(BaseModel):
    source: Optional[str] = None
    page: Optional[int] = None
    category: Optional[str] = None
    document_id: Optional[str] = None
    jurisdiction: List[str] = Field(default_factory=list)


class ChunkOut(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChunksResponse(BaseModel):
    region: str
    chunks: List[ChunkOut]
    total: int


class IngestResponse(BaseModel):
    ok: bool
    jurisdiction: str
    message: str


class CheckRequest(BaseModel):
    consent_text: str = Field(max_length=200_000)
    store_dir: Optional[str] = None
    category: Optional[str] = None
    jurisdictions: List[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=8, ge=3, le=16)


class CheckResponse(BaseModel):
    report: Dict[str, Any]
    chunks: List[ChunkOut]
    scope: str
    chunk_count: int


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20_000)


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(max_length=100)
    chunks: List[Dict[str, Any]] = Field(default_factory=list, max_length=100)
    consent_text: str = Field(default="", max_length=200_000)
    store_dir: Optional[str] = None
    jurisdictions: List[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=8, ge=3, le=16)
    category: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    chunks: List[ChunkOut] = Field(default_factory=list)
    scope: str = ""


class StoreMetaResponse(BaseModel):
    store_dir: str
    jurisdictions: List[str]
    corpus_document_count: int
    manifest_chunk_count: int
    retrieval_ready: bool
    llm_hint: str
