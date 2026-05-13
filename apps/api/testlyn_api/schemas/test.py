from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TestConfig(BaseModel):
    vus: int = 1
    duration_seconds: int = 30
    thresholds: dict[str, list[str]] = {}


class TestCreate(BaseModel):
    name: str
    product: str = "load"
    script_inline: str | None = None
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
