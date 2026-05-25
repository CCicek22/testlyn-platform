from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Matches Test.name -> String(255) and Test.script_inline -> Text (unbounded).
_NAME_MAX_LENGTH = 200
_SCRIPT_MAX_LENGTH = 1_000_000


class TestConfig(BaseModel):
    vus: int = Field(1, gt=0)
    duration_seconds: int = Field(30, gt=0)
    thresholds: dict[str, list[str]] = {}


class TestCreate(BaseModel):
    name: str = Field(..., max_length=_NAME_MAX_LENGTH)
    product: str = "load"
    script_inline: str | None = Field(default=None, max_length=_SCRIPT_MAX_LENGTH)
    config: TestConfig = TestConfig()


class TestPatch(BaseModel):
    name: str | None = None
    script_inline: str | None = None
    config: TestConfig | None = None


class TestOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    product: str
    script_uri: str | None
    script_inline: str | None
    config: dict[str, Any]
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
