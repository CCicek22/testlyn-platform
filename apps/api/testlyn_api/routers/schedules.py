from __future__ import annotations

import uuid

import structlog
from croniter import croniter
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.models.test import Test
from testlyn_api.services import scheduler as svc

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["schedules"])

# In-memory handle registry for Phase 1 (no DB table for schedules yet).
# Maps handle.id -> ScheduleHandle. Survives only within process lifetime.
_registry: dict[str, svc.ScheduleHandle] = {}


class ScheduleCreate(BaseModel):
    cron: str
    timezone: str = "UTC"

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"cron must have exactly 5 fields (got {len(parts)}): '{v}'"
            )
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: '{v}'")
        return v


class ScheduleOut(BaseModel):
    id: str
    test_id: str
    org_id: str
    cron: str
    timezone: str
    local: bool


def _handle_to_out(h: svc.ScheduleHandle) -> ScheduleOut:
    return ScheduleOut(
        id=h.id,
        test_id=h.test_id,
        org_id=h.org_id,
        cron=h.cron,
        timezone=h.timezone,
        local=h.local,
    )


@router.post(
    "/tests/{test_id}/schedule",
    response_model=ScheduleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    test_id: uuid.UUID,
    body: ScheduleCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> ScheduleOut:
    result = await session.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test not found")

    # Derive org_id from test -> project -> org
    from sqlalchemy import select as sa_select

    from testlyn_api.models.project import Project

    proj_result = await session.execute(sa_select(Project).where(Project.id == test.project_id))
    project = proj_result.scalar_one_or_none()
    org_id = str(project.org_id) if project else ""

    handle = await svc.create_schedule(
        test_id=str(test_id),
        cron=body.cron,
        tz=body.timezone,
        org_id=org_id,
    )
    _registry[handle.id] = handle
    log.info("schedule.created", handle_id=handle.id, test_id=str(test_id))
    return _handle_to_out(handle)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    handle = _registry.get(schedule_id)
    if handle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    await svc.delete_schedule(handle)
    _registry.pop(schedule_id, None)
    log.info("schedule.deleted", handle_id=schedule_id)


@router.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    org_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> list[ScheduleOut]:
    handles = await svc.list_schedules(org_id)
    # Merge with local registry to cover local-mode handles not returned by cloud
    local_handles = [h for h in _registry.values() if h.org_id == org_id]
    cloud_ids = {h.id for h in handles}
    for lh in local_handles:
        if lh.id not in cloud_ids:
            handles.append(lh)
    return [_handle_to_out(h) for h in handles]
