from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    consent_text: str
    store_dir: Optional[str] = None
    category: Optional[str] = None
    jurisdictions: List[str] = Field(default_factory=list)
    top_k: int = Field(default=8, ge=3, le=16)


class CheckResponse(BaseModel):
    report: Dict[str, Any]
    chunks: List[ChunkOut]
    scope: str
    chunk_count: int


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    chunks: List[Dict[str, Any]]
    consent_text: str = ""
    store_dir: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str


class StoreMetaResponse(BaseModel):
    store_dir: str
    jurisdictions: List[str]
    corpus_document_count: int
    llm_hint: str
