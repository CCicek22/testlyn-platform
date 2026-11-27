from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    source: str = Field(min_length=1, max_length=40)
    text: str
    project_id: uuid.UUID | None = None


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
