from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def clear_local_store():
    """Clear the in-memory scheduler store between tests."""
    from testlyn_api.services import scheduler

    scheduler._local_store.clear()
    yield
    scheduler._local_store.clear()


class TestLocalMode:
    """All tests run with GCP creds unavailable → local-mode fallback."""

    @pytest.fixture(autouse=True)
    def no_gcp_creds(self):
        import google.auth.exceptions

        with patch("google.auth.default", side_effect=google.auth.exceptions.DefaultCredentialsError()):
            yield

    async def test_create_returns_handle(self):
        from testlyn_api.services.scheduler import create_schedule

        handle = await create_schedule(
            test_id=str(uuid.uuid4()),
            cron="0 * * * *",
            tz="UTC",
            org_id="org-001",
        )

        assert handle.local is True
        assert handle.cron == "0 * * * *"
        assert handle.timezone == "UTC"
        assert handle.org_id == "org-001"

    async def test_create_stores_in_registry(self):
        from testlyn_api.services import scheduler

        handle = await scheduler.create_schedule(
            test_id=str(uuid.uuid4()),
            cron="30 6 * * 1",
            tz="America/New_York",
            org_id="org-002",
        )

        assert handle.id in scheduler._local_store

    async def test_delete_removes_from_registry(self):
        from testlyn_api.services import scheduler

        handle = await scheduler.create_schedule(
            test_id=str(uuid.uuid4()),
            cron="0 12 * * *",
            tz="UTC",
            org_id="org-003",
        )
        assert handle.id in scheduler._local_store

        await scheduler.delete_schedule(handle)
        assert handle.id not in scheduler._local_store

    async def test_list_returns_org_schedules(self):
        from testlyn_api.services import scheduler

        org_id = "org-list-test"
        other_org = "org-other"

        h1 = await scheduler.create_schedule(
            test_id=str(uuid.uuid4()), cron="0 1 * * *", tz="UTC", org_id=org_id
        )
        h2 = await scheduler.create_schedule(
            test_id=str(uuid.uuid4()), cron="0 2 * * *", tz="UTC", org_id=org_id
        )
        await scheduler.create_schedule(
            test_id=str(uuid.uuid4()), cron="0 3 * * *", tz="UTC", org_id=other_org
        )

        handles = await scheduler.list_schedules(org_id)
        ids = {h.id for h in handles}
        assert h1.id in ids
        assert h2.id in ids
        assert len(ids) == 2

    async def test_list_empty_for_unknown_org(self):
        from testlyn_api.services.scheduler import list_schedules

        handles = await list_schedules("org-nonexistent")
        assert handles == []


class TestCloudTarget:
    """Cloud-mode create_schedule must point at the internal endpoint and carry
    the X-Internal-Token header, otherwise every scheduled trigger 401s."""

    async def test_target_uses_internal_path_and_token_header(self, monkeypatch):
        from testlyn_api.services import scheduler

        captured: dict = {}

        class _FakeClient:
            async def create_job(self, *, request):
                captured["job"] = request.job

        async def _fake_try(*args, **kwargs):
            return _FakeClient()

        monkeypatch.setattr(scheduler, "_try_cloud_scheduler", _fake_try)

        from testlyn_api.config import get_settings

        cloud = get_settings().model_copy(update={"internal_token": "tok-123"})
        monkeypatch.setattr(scheduler, "get_settings", lambda: cloud)

        test_id = str(uuid.uuid4())
        handle = await scheduler.create_schedule(
            test_id=test_id, cron="0 * * * *", tz="UTC", org_id="org-x"
        )

        assert handle.local is False
        job = captured["job"]
        assert job.http_target.uri.endswith(f"/v1/internal/tests/{test_id}/runs")
        assert job.http_target.headers["X-Internal-Token"] == "tok-123"


class _FakeJob:
    def __init__(self, name: str, description: str = "", schedule: str = "0 * * * *",
                 time_zone: str = "UTC") -> None:
        self.name = name
        self.description = description
        self.schedule = schedule
        self.time_zone = time_zone


async def _aiter(jobs):
    for job in jobs:
        yield job


class TestCloudTenantIsolation:
    """Cloud-mode list/get must attribute jobs via the org marker in the job
    description — never stamp the requesting org onto foreign jobs."""

    async def test_create_writes_org_marker_in_description(self, monkeypatch):
        from testlyn_api.services import scheduler

        captured: dict = {}

        class _FakeClient:
            async def create_job(self, *, request):
                captured["job"] = request.job

        async def _fake_try(*args, **kwargs):
            return _FakeClient()

        monkeypatch.setattr(scheduler, "_try_cloud_scheduler", _fake_try)

        test_id = str(uuid.uuid4())
        await scheduler.create_schedule(
            test_id=test_id, cron="0 * * * *", tz="UTC", org_id="org-desc"
        )
        desc = captured["job"].description
        assert "org_id=org-desc" in desc
        assert f"test_id={test_id}" in desc

    async def test_list_filters_jobs_to_requesting_org(self, monkeypatch):
        from testlyn_api.services import scheduler

        prefix = "projects/p/locations/l/jobs/testlyn-sched-"
        jobs = [
            _FakeJob(f"{prefix}h1", "testlyn org_id=org-a test_id=t1"),
            _FakeJob(f"{prefix}h2", "testlyn org_id=org-b test_id=t2"),
            _FakeJob(f"{prefix}h3", ""),  # legacy job without marker
            _FakeJob("projects/p/locations/l/jobs/unrelated", ""),
        ]

        class _FakeClient:
            async def list_jobs(self, *, request):
                return _aiter(jobs)

        async def _fake_try(*args, **kwargs):
            return _FakeClient()

        monkeypatch.setattr(scheduler, "_try_cloud_scheduler", _fake_try)

        handles = await scheduler.list_schedules("org-a")
        assert [h.id for h in handles] == ["h1"]
        assert handles[0].org_id == "org-a"
        assert handles[0].test_id == "t1"

        # The unmarked legacy job is attributed to NO org (no cross-tenant leak).
        assert await scheduler.list_schedules("org-c") == []

    async def test_get_schedule_reconstructs_handle_from_cloud(self, monkeypatch):
        """Delete must work statelessly: a handle can be rebuilt from the
        deterministically-named job + its description marker (no registry)."""
        from testlyn_api.services import scheduler

        requested: dict = {}

        class _FakeClient:
            async def get_job(self, *, request):
                requested["name"] = request.name
                return _FakeJob(
                    request.name,
                    "testlyn org_id=org-z test_id=t9",
                    schedule="30 6 * * 1",
                    time_zone="America/New_York",
                )

        async def _fake_try(*args, **kwargs):
            return _FakeClient()

        monkeypatch.setattr(scheduler, "_try_cloud_scheduler", _fake_try)

        handle = await scheduler.get_schedule("handle-42")
        assert handle is not None
        assert requested["name"].endswith("testlyn-sched-handle-42")
        assert handle.org_id == "org-z"
        assert handle.test_id == "t9"
        assert handle.cron == "30 6 * * 1"
        assert handle.local is False

    async def test_get_schedule_without_org_marker_returns_none(self, monkeypatch):
        from testlyn_api.services import scheduler

        class _FakeClient:
            async def get_job(self, *, request):
                return _FakeJob(request.name, "")  # no marker → can't authorize

        async def _fake_try(*args, **kwargs):
            return _FakeClient()

        monkeypatch.setattr(scheduler, "_try_cloud_scheduler", _fake_try)
        assert await scheduler.get_schedule("handle-x") is None


class TestDeleteRegistryFallback:
    """DELETE /v1/schedules/{id} must not depend on the in-process router
    registry (empty on other instances / after restart): it falls back to
    resolving the handle via the scheduler service."""

    @pytest.fixture(autouse=True)
    def no_gcp_creds(self):
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            yield

    async def test_delete_succeeds_with_empty_registry(self, client, db_session):
        from testlyn_api.models.project import Project
        from testlyn_api.models.test import Test as TestModel
        from testlyn_api.routers import schedules as schedules_router

        dev_org_id = uuid.UUID("00000000-0000-0000-0000-d3eff3e10102")
        proj = Project(org_id=dev_org_id, name="SchedP", slug=f"sched-{uuid.uuid4().hex[:6]}")
        db_session.add(proj)
        await db_session.flush()
        test = TestModel(
            project_id=proj.id, name="SchedT", script_inline="export default function(){}"
        )
        db_session.add(test)
        await db_session.commit()

        create_resp = await client.post(
            f"/v1/tests/{test.id}/schedule", json={"cron": "0 * * * *"}
        )
        assert create_resp.status_code == 201, create_resp.text
        schedule_id = create_resp.json()["id"]

        # Simulate another instance / a restart: in-process registry is empty.
        schedules_router._registry.clear()

        del_resp = await client.delete(f"/v1/schedules/{schedule_id}")
        assert del_resp.status_code == 204, del_resp.text


class TestCronValidation:
    """Validates cron expressions in the schedules router."""

    @pytest.mark.parametrize(
        "cron,should_pass",
        [
            ("0 * * * *", True),
            ("*/5 * * * *", True),
            ("30 6 * * 1-5", True),
            ("* * * *", False),  # only 4 fields
            ("* * * * * *", False),  # 6 fields
            ("", False),
            ("not a cron", False),
        ],
    )
    def test_cron_validation(self, cron: str, should_pass: bool):
        from pydantic import ValidationError
        from testlyn_api.routers.schedules import ScheduleCreate

        if should_pass:
            obj = ScheduleCreate(cron=cron)
            assert obj.cron == cron
        else:
            with pytest.raises(ValidationError):
                ScheduleCreate(cron=cron)

    def test_four_field_cron_rejected(self):
        """Explicitly verify '* * * *' is rejected (too few fields)."""
        from pydantic import ValidationError
        from testlyn_api.routers.schedules import ScheduleCreate

        with pytest.raises(ValidationError, match="5 fields"):
            ScheduleCreate(cron="* * * *")
