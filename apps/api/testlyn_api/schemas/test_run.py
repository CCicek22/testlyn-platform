from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class RunCreate(BaseModel):
    pass  # No body required for Phase 1


class RunOut(BaseModel):
    id: uuid.UUID
    test_id: uuid.UUID
    product: str
    state: str
    runner_id: str | None
    region: str
    started_at: datetime | None
    finished_at: datetime | None
    summary_uri: str | None
    error_reason: str | None
    triggered_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunCompletePayload(BaseModel):
    exit_code: int
    summary_uri: str | None = None
    error_reason: str | None = None
