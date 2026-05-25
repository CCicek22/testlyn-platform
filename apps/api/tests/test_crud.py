from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_org(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/orgs",
        json={"name": "Acme Corp"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Acme Corp"
    assert data["slug"].startswith("acme-corp")
    assert "id" in data


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient) -> None:
    # Create org first
    org_resp = await client.post("/v1/orgs", json={"name": "Test Org"})
    assert org_resp.status_code == 201
    org_id = org_resp.json()["id"]

    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "My Project", "slug": "my-project"},
    )
    assert proj_resp.status_code == 201
    data = proj_resp.json()
    assert data["name"] == "My Project"
    assert data["org_id"] == org_id


@pytest.mark.asyncio
async def test_create_test(client: AsyncClient) -> None:
    org_resp = await client.post("/v1/orgs", json={"name": "Org2"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "Proj2", "slug": "proj2"}
    )
    proj_id = proj_resp.json()["id"]

    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Smoke test",
            "script_inline": "import http from 'k6/http'; export default function() {}",
            "config": {"vus": 2, "duration_seconds": 10},
        },
    )
    assert test_resp.status_code == 201
    data = test_resp.json()
    assert data["name"] == "Smoke test"
    assert data["product"] == "load"


@pytest.mark.asyncio
async def test_create_run(client: AsyncClient, monkeypatch) -> None:
    # Stub out enqueue_run to avoid actual http call in test
    from testlyn_api.core import tasks

    async def _noop(run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    # Scaffold org → project → test
    org_resp = await client.post("/v1/orgs", json={"name": "Org3"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "Proj3", "slug": "proj3"}
    )
    proj_id = proj_resp.json()["id"]
    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Load test",
            "script_inline": "import http from 'k6/http'; export default function() {}",
            "config": {"vus": 1, "duration_seconds": 5},
        },
    )
    test_id = test_resp.json()["id"]

    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert run_resp.status_code == 201
    data = run_resp.json()
    assert data["state"] == "queued"
    assert data["test_id"] == test_id


@pytest.mark.asyncio
async def test_get_run(client: AsyncClient, monkeypatch) -> None:
    from testlyn_api.core import tasks

    async def _noop(run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_resp = await client.post("/v1/orgs", json={"name": "Org4"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "Proj4", "slug": "proj4"}
    )
    proj_id = proj_resp.json()["id"]
    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Get run test",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 5},
        },
    )
    test_id = test_resp.json()["id"]
    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    run_id = run_resp.json()["id"]

    get_resp = await client.get(f"/v1/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == run_id


# ---------------------------------------------------------------------------
# RunOut config field tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_run_response_includes_config(client: AsyncClient, monkeypatch) -> None:
    """POST /v1/tests/{id}/runs → RunOut.config is populated from the parent Test."""
    from testlyn_api.core import tasks

    async def _noop(_run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_resp = await client.post("/v1/orgs", json={"name": "ConfigOrg1"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "ConfigProj1", "slug": "config-proj-1"}
    )
    proj_id = proj_resp.json()["id"]
    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Config run test",
            "script_inline": "export default function() {}",
            "config": {"vus": 5, "duration_seconds": 120},
        },
    )
    assert test_resp.status_code == 201
    test_id = test_resp.json()["id"]

    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert run_resp.status_code == 201
    data = run_resp.json()
    assert "config" in data
    assert data["config"]["vus"] == 5
    assert data["config"]["duration_seconds"] == 120


@pytest.mark.asyncio
async def test_get_run_response_includes_config(client: AsyncClient, monkeypatch) -> None:
    """GET /v1/runs/{id} → RunOut.config is populated from the parent Test."""
    from testlyn_api.core import tasks

    async def _noop(_run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_resp = await client.post("/v1/orgs", json={"name": "ConfigOrg2"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "ConfigProj2", "slug": "config-proj-2"}
    )
    proj_id = proj_resp.json()["id"]
    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Get run config test",
            "script_inline": "export default function() {}",
            "config": {"vus": 3, "duration_seconds": 60},
        },
    )
    test_id = test_resp.json()["id"]
    run_resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    run_id = run_resp.json()["id"]

    get_resp = await client.get(f"/v1/runs/{run_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "config" in data
    assert data["config"]["vus"] == 3
    assert data["config"]["duration_seconds"] == 60


@pytest.mark.asyncio
async def test_list_runs_response_includes_config(client: AsyncClient, monkeypatch) -> None:
    """GET /v1/runs?product=load → each RunOut.config is populated from its parent Test."""
    from testlyn_api.core import tasks

    async def _noop(_run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_resp = await client.post("/v1/orgs", json={"name": "ConfigOrg3"})
    org_id = org_resp.json()["id"]
    proj_resp = await client.post(
        f"/v1/orgs/{org_id}/projects", json={"name": "ConfigProj3", "slug": "config-proj-3"}
    )
    proj_id = proj_resp.json()["id"]
    test_resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "List runs config test",
            "script_inline": "export default function() {}",
            "config": {"vus": 10, "duration_seconds": 300},
        },
    )
    test_id = test_resp.json()["id"]
    await client.post(f"/v1/tests/{test_id}/runs", json={})

    list_resp = await client.get("/v1/runs?product=load")
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert len(runs) >= 1
    run = next(r for r in runs if r["test_id"] == test_id)
    assert "config" in run
    assert run["config"]["vus"] == 10
    assert run["config"]["duration_seconds"] == 300


# ---------------------------------------------------------------------------
# Negative-path (404 / 422) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nonexistent_org_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/orgs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_test_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/tests/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_run_returns_404(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/runs/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_org_missing_name_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/v1/orgs", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_test_nonexistent_project_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        f"/v1/projects/{uuid.uuid4()}/tests",
        json={
            "name": "Ghost Test",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 5},
        },
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_project_nonexistent_org_returns_404(client: AsyncClient) -> None:
    resp = await client.post(
        f"/v1/orgs/{uuid.uuid4()}/projects",
        json={"name": "Ghost Project", "slug": "ghost-project"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# list_runs ordering (fix: order by created_at, not random uuid id)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_orders_most_recent_first(client: AsyncClient, monkeypatch) -> None:
    """GET /v1/runs returns runs newest-first by created_at, not by random uuid."""
    from datetime import UTC, datetime, timedelta

    from testlyn_api.core import tasks
    from testlyn_api.models.test_run import TestRun

    async def _noop(_run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id = (await client.post("/v1/orgs", json={"name": "OrderOrg"})).json()["id"]
    proj_id = (
        await client.post(
            f"/v1/orgs/{org_id}/projects", json={"name": "OrderProj", "slug": "order-proj"}
        )
    ).json()["id"]
    test_id = (
        await client.post(
            f"/v1/projects/{proj_id}/tests",
            json={
                "name": "Order test",
                "script_inline": "export default function() {}",
                "config": {"vus": 1, "duration_seconds": 5},
            },
        )
    ).json()["id"]

    # Create three runs and stamp distinct created_at values out of insertion order.
    run_ids = []
    for _ in range(3):
        rid = (await client.post(f"/v1/tests/{test_id}/runs", json={})).json()["id"]
        run_ids.append(uuid.UUID(rid))

    # Force created_at ordering: run_ids[1] newest, then run_ids[0], then run_ids[2].
    from sqlalchemy import select as _select

    base = datetime(2026, 1, 1, tzinfo=UTC)
    stamps = {run_ids[1]: base + timedelta(hours=3), run_ids[0]: base + timedelta(hours=2), run_ids[2]: base + timedelta(hours=1)}
    # Use a fresh app-bound session via the override is not trivial here, so reach
    # into the same session the client uses through a direct query patch.
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as s:
        for rid, ts in stamps.items():
            run = (await s.execute(_select(TestRun).where(TestRun.id == rid))).scalar_one()
            run.created_at = ts
        await s.commit()

    resp = await client.get("/v1/runs?product=load")
    assert resp.status_code == 200
    returned = [uuid.UUID(r["id"]) for r in resp.json()]
    # Newest first: run_ids[1], run_ids[0], run_ids[2]
    assert returned[:3] == [run_ids[1], run_ids[0], run_ids[2]]


# ---------------------------------------------------------------------------
# TestCreate / TestConfig input validation (fix: reject <=0 vus/duration,
# cap name + script length)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_test_zero_vus_returns_422(client: AsyncClient) -> None:
    org_id = (await client.post("/v1/orgs", json={"name": "VuOrg"})).json()["id"]
    proj_id = (
        await client.post(f"/v1/orgs/{org_id}/projects", json={"name": "VuProj", "slug": "vu-proj"})
    ).json()["id"]
    resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Bad vus",
            "script_inline": "export default function() {}",
            "config": {"vus": 0, "duration_seconds": 5},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_test_negative_duration_returns_422(client: AsyncClient) -> None:
    org_id = (await client.post("/v1/orgs", json={"name": "DurOrg"})).json()["id"]
    proj_id = (
        await client.post(
            f"/v1/orgs/{org_id}/projects", json={"name": "DurProj", "slug": "dur-proj"}
        )
    ).json()["id"]
    resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "Bad duration",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": -5},
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_test_overlong_name_returns_422(client: AsyncClient) -> None:
    org_id = (await client.post("/v1/orgs", json={"name": "NameOrg"})).json()["id"]
    proj_id = (
        await client.post(
            f"/v1/orgs/{org_id}/projects", json={"name": "NameProj", "slug": "name-proj"}
        )
    ).json()["id"]
    resp = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "x" * 201,
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 5},
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# list_tests pagination (fix: bounded limit/offset)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tests_respects_limit(client: AsyncClient) -> None:
    org_id = (await client.post("/v1/orgs", json={"name": "PageOrg"})).json()["id"]
    proj_id = (
        await client.post(
            f"/v1/orgs/{org_id}/projects", json={"name": "PageProj", "slug": "page-proj"}
        )
    ).json()["id"]
    for i in range(3):
        await client.post(
            f"/v1/projects/{proj_id}/tests",
            json={
                "name": f"T{i}",
                "script_inline": "export default function() {}",
                "config": {"vus": 1, "duration_seconds": 5},
            },
        )

    resp = await client.get(f"/v1/projects/{proj_id}/tests?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # Cap enforced: limit above 200 is rejected.
    resp_over = await client.get(f"/v1/projects/{proj_id}/tests?limit=500")
    assert resp_over.status_code == 422


@pytest.mark.asyncio
async def test_list_tests_offset_pages(client: AsyncClient) -> None:
    org_id = (await client.post("/v1/orgs", json={"name": "OffOrg"})).json()["id"]
    proj_id = (
        await client.post(f"/v1/orgs/{org_id}/projects", json={"name": "OffProj", "slug": "off-proj"})
    ).json()["id"]
    for i in range(3):
        await client.post(
            f"/v1/projects/{proj_id}/tests",
            json={
                "name": f"O{i}",
                "script_inline": "export default function() {}",
                "config": {"vus": 1, "duration_seconds": 5},
            },
        )

    page1 = await client.get(f"/v1/projects/{proj_id}/tests?limit=2&offset=0")
    page2 = await client.get(f"/v1/projects/{proj_id}/tests?limit=2&offset=2")
    assert len(page1.json()) == 2
    assert len(page2.json()) == 1
    ids1 = {t["id"] for t in page1.json()}
    ids2 = {t["id"] for t in page2.json()}
    assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# list_runs current-membership recheck (fix: user removed from org no longer
# sees runs they triggered there)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_hidden_after_org_removal(client: AsyncClient, monkeypatch) -> None:
    from sqlalchemy import delete, select as _select

    from testlyn_api.core import tasks
    from testlyn_api.models.org import OrgMember

    async def _noop(_run_id):
        pass

    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id = (await client.post("/v1/orgs", json={"name": "RemoveOrg"})).json()["id"]
    proj_id = (
        await client.post(
            f"/v1/orgs/{org_id}/projects", json={"name": "RemoveProj", "slug": "remove-proj"}
        )
    ).json()["id"]
    test_id = (
        await client.post(
            f"/v1/projects/{proj_id}/tests",
            json={
                "name": "Remove test",
                "script_inline": "export default function() {}",
                "config": {"vus": 1, "duration_seconds": 5},
            },
        )
    ).json()["id"]
    run_id = (await client.post(f"/v1/tests/{test_id}/runs", json={})).json()["id"]

    # While a member, the run is visible.
    visible = await client.get("/v1/runs?product=load")
    assert run_id in {r["id"] for r in visible.json()}

    # Remove the current user's membership in that org.
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as s:
        member = (
            await s.execute(
                _select(OrgMember).where(OrgMember.org_id == uuid.UUID(org_id))
            )
        ).scalar_one()
        await s.execute(delete(OrgMember).where(OrgMember.id == member.id))
        await s.commit()

    # Now the run must no longer appear.
    after = await client.get("/v1/runs?product=load")
    assert run_id not in {r["id"] for r in after.json()}
