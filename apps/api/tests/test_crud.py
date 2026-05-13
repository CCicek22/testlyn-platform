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
