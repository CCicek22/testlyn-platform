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
