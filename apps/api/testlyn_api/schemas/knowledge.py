from __future__ import annotations

import uuid
from datetime import datetime

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
