from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)

# In-memory fallback store: {job_name: ScheduleHandle}
_local_store: dict[str, ScheduleHandle] = {}


@dataclass
class ScheduleHandle:
    id: str  # Cloud Scheduler job name or local key
    test_id: str
    org_id: str
    cron: str
    timezone: str
    local: bool = field(default=False)


def _job_name(test_id: str, handle_id: str) -> str:
    settings = get_settings()
    project = settings.gcp_project_id
    location = settings.vertex_ai_location
    return f"projects/{project}/locations/{location}/jobs/testlyn-sched-{handle_id}"


def _job_description(org_id: str, test_id: str) -> str:
    """Tenancy marker stored on the Cloud Scheduler job.

    Cloud Scheduler jobs don't support labels, so org/test ownership is encoded
    in the description. ``list_schedules``/``get_schedule`` parse it back — a
    job without this marker is never attributed to any org.
    """
    return f"testlyn org_id={org_id} test_id={test_id}"


def _parse_job_metadata(description: str) -> dict[str, str]:
    """Parse ``org_id=...``/``test_id=...`` tokens from a job description."""
    meta: dict[str, str] = {}
    for token in (description or "").split():
        key, sep, value = token.partition("=")
        if sep and key in ("org_id", "test_id") and value:
            meta[key] = value
    return meta


async def _try_cloud_scheduler() -> Any | None:
    """Return a Cloud Scheduler client or None if creds unavailable."""
    try:
        import google.auth
        import google.auth.exceptions

        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

        from google.cloud import scheduler_v1

        return scheduler_v1.CloudSchedulerAsyncClient()
    except Exception:
        return None


async def create_schedule(test_id: str, cron: str, tz: str, *, org_id: str) -> ScheduleHandle:
    """Create a Cloud Scheduler job that triggers a test run. Falls back to local store."""
    settings = get_settings()
    handle_id = str(uuid.uuid4())
    client = await _try_cloud_scheduler()

    if client is None:
        log.warning(
            "scheduler_creds_missing",
            scheduler_event="local_mode",
            test_id=test_id,
            detail="GCP credentials unavailable; using in-memory scheduler",
        )
        handle = ScheduleHandle(
            id=handle_id,
            test_id=test_id,
            org_id=org_id,
            cron=cron,
            timezone=tz,
            local=True,
        )
        _local_store[handle_id] = handle
        return handle

    from google.cloud import scheduler_v1

    project = settings.gcp_project_id
    location = settings.vertex_ai_location
    parent = f"projects/{project}/locations/{location}"
    job_name = _job_name(test_id, handle_id)

    # Hit the internal run endpoint guarded by X-Internal-Token. Scheduler HTTP
    # targets can't carry a Firebase bearer + RBAC, so the user-facing
    # /v1/tests/{id}/runs would 401 every trigger. The internal path derives org
    # from the test row and is authed by the shared secret.
    target_url = f"{settings.api_base_url}/v1/internal/tests/{test_id}/runs"
    job = scheduler_v1.Job(
        name=job_name,
        description=_job_description(org_id, test_id),
        schedule=cron,
        time_zone=tz,
        http_target=scheduler_v1.HttpTarget(
            uri=target_url,
            http_method=scheduler_v1.HttpMethod.POST,
            headers={"X-Internal-Token": settings.internal_token},
        ),
    )
    request = scheduler_v1.CreateJobRequest(parent=parent, job=job)
    await client.create_job(request=request)

    handle = ScheduleHandle(
        id=handle_id,
        test_id=test_id,
        org_id=org_id,
        cron=cron,
        timezone=tz,
        local=False,
    )
    log.info("scheduler.created", job_name=job_name, test_id=test_id)
    return handle


async def delete_schedule(handle: ScheduleHandle) -> None:
    """Delete a Cloud Scheduler job (or remove from local store)."""
    if handle.local:
        _local_store.pop(handle.id, None)
        log.info("scheduler.deleted_local", handle_id=handle.id)
        return

    client = await _try_cloud_scheduler()
    if client is None:
        log.warning("scheduler.delete_no_creds", handle_id=handle.id)
        return

    from google.cloud import scheduler_v1

    job_name = _job_name(handle.test_id, handle.id)
    request = scheduler_v1.DeleteJobRequest(name=job_name)
    await client.delete_job(request=request)
    log.info("scheduler.deleted", job_name=job_name)


async def list_schedules(org_id: str) -> list[ScheduleHandle]:
    """List schedules for an org. Local mode returns in-memory entries."""
    client = await _try_cloud_scheduler()

    if client is None:
        log.warning(
            "scheduler_creds_missing",
            scheduler_event="local_mode",
            org_id=org_id,
            detail="GCP credentials unavailable; returning in-memory schedules",
        )
        return [h for h in _local_store.values() if h.org_id == org_id]

    settings = get_settings()
    from google.cloud import scheduler_v1

    project = settings.gcp_project_id
    location = settings.vertex_ai_location
    parent = f"projects/{project}/locations/{location}"
    request = scheduler_v1.ListJobsRequest(parent=parent)

    handles: list[ScheduleHandle] = []
    async for job in await client.list_jobs(request=request):
        # Filter by naming convention: testlyn-sched-*
        if "testlyn-sched-" not in job.name:
            continue
        handle_id = job.name.split("testlyn-sched-")[-1]
        # Tenant isolation: only return jobs whose description marker matches
        # the requesting org. Jobs without a marker (pre-marker legacy) are
        # skipped — never stamp the requesting org's id onto a foreign job.
        meta = _parse_job_metadata(job.description)
        if meta.get("org_id") != org_id:
            continue
        handles.append(
            ScheduleHandle(
                id=handle_id,
                test_id=meta.get("test_id", ""),
                org_id=org_id,
                cron=job.schedule,
                timezone=job.time_zone,
                local=False,
            )
        )
    return handles


async def get_schedule(handle_id: str) -> ScheduleHandle | None:
    """Resolve a handle by id — local store first, then Cloud Scheduler.

    Cloud job names are deterministic (``testlyn-sched-<handle_id>``), so a
    handle can be reconstructed on any instance / after a restart without the
    in-process registry — this is what keeps cloud schedules deletable.
    Returns ``None`` if the job doesn't exist or carries no org marker (a
    handle without an org can't be authorized).
    """
    local = _local_store.get(handle_id)
    if local is not None:
        return local

    client = await _try_cloud_scheduler()
    if client is None:
        return None

    from google.cloud import scheduler_v1

    job_name = _job_name("", handle_id)
    try:
        job = await client.get_job(request=scheduler_v1.GetJobRequest(name=job_name))
    except Exception:
        log.info("scheduler.get_not_found", handle_id=handle_id)
        return None

    meta = _parse_job_metadata(job.description)
    org_id = meta.get("org_id")
    if not org_id:
        return None
    return ScheduleHandle(
        id=handle_id,
        test_id=meta.get("test_id", ""),
        org_id=org_id,
        cron=job.schedule,
        timezone=job.time_zone,
        local=False,
    )
