from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from testlyn_api.models.target import TargetKind


class TargetCreate(BaseModel):
    name: str
    kind: TargetKind
    base_url: str | None = None
    auth_config: dict[str, Any] | None = None


class TargetUpdate(BaseModel):
    name: str | None = None
    kind: TargetKind | None = None
    base_url: str | None = None
    auth_config: dict[str, Any] | None = None


class TargetOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    kind: TargetKind
    base_url: str | None
    auth_config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TargetListOut(BaseModel):
    items: list[TargetOut]
    total: int
    cursor: uuid.UUID | None
