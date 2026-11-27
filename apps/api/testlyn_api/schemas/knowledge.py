from __future__ import annotations

import uuid
from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _require_storable_text(value: str) -> str:
    """Postgres rejects NUL bytes; lone surrogates cannot be encoded as UTF-8."""
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("must be valid Unicode (no lone surrogates)") from exc
    return value


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=40)
    text: str
    project_id: uuid.UUID | None = None

    @field_validator("title", "source", "text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        return _require_storable_text(value)


class KnowledgeChunkOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    heading: str | None
    text: str
    char_start: int
    char_end: int
    token_estimate: int
    embedding_model: str

    model_config = {"from_attributes": True}


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    project_id: uuid.UUID | None
    title: str
    source: str
    status: str
    chunk_count: int
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeDocumentDetail(KnowledgeDocumentOut):
    chunks: list[KnowledgeChunkOut]


class KnowledgeSearchRequest(BaseModel):
    query: str
    project_id: uuid.UUID | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid"

    @field_validator("query")
    @classmethod
    def _check_query(cls, value: str) -> str:
        value = _require_storable_text(value).strip()
        if not 1 <= len(value) <= 1000:
            raise ValueError("query must be 1 to 1000 characters after trimming")
        return value


class KnowledgeSearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source: str
    heading: str | None
    text: str
    char_start: int
    char_end: int
    score: float
    vector_rank: int | None
    keyword_rank: int | None

    model_config = {"from_attributes": True}


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeSearchResult]
    mode: str
    reranked: bool
