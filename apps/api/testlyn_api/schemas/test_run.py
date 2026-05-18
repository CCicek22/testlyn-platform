from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from testlyn_api.schemas.test import TestConfig

if TYPE_CHECKING:
    from testlyn_api.models.test import Test
    from testlyn_api.models.test_run import TestRun


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
    config: TestConfig

    model_config = {"from_attributes": True}

    @classmethod
    def from_run_and_test(cls, run: TestRun, test: Test) -> RunOut:
        """Build a RunOut, populating config from the parent Test record."""
        raw_config: dict = test.config or {}
        return cls(
            id=run.id,
            test_id=run.test_id,
            product=run.product,
            state=run.state,
            runner_id=run.runner_id,
            region=run.region,
            started_at=run.started_at,
            finished_at=run.finished_at,
            summary_uri=run.summary_uri,
            error_reason=run.error_reason,
            triggered_by=run.triggered_by,
            created_at=run.created_at,
            updated_at=run.updated_at,
            config=TestConfig(**raw_config),
        )


class RunCompletePayload(BaseModel):
    exit_code: int
    summary_uri: str | None = None
    error_reason: str | None = None
