from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import OrgMember
from testlyn_api.models.runner_registry import RunnerRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_org(client: AsyncClient, name: str = "Test Org") -> str:
    resp = await client.post("/v1/orgs", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _seed_runner_registry(db_session: AsyncSession) -> None:
    """Seed minimal runners_registry rows for dispatcher tests."""
    rows = [
        RunnerRegistry(name="k6", product="load", image_uri="grafana/k6:1.3.0"),
        RunnerRegistry(
            name="playwright",
            product="functional",
            image_uri="mcr.microsoft.com/playwright:v1.50.0-noble",
        ),
        RunnerRegistry(
            name="axe-core",
            product="a11y",
            image_uri="ghcr.io/testlyn/engine-a11y:dev",
        ),
    ]
    for row in rows:
        db_session.add(row)
    await db_session.commit()


# ---------------------------------------------------------------------------
# CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_target(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org A")
    resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "prod-web", "kind": "web", "base_url": "https://example.com"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "prod-web"
    assert data["kind"] == "web"
    assert data["base_url"] == "https://example.com"
    assert data["org_id"] == org_id
    assert "id" in data


@pytest.mark.asyncio
async def test_get_target(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org B")
    create_resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "api-target", "kind": "api"},
    )
    assert create_resp.status_code == 201
    target_id = create_resp.json()["id"]

    get_resp = await client.get(f"/v1/targets/{target_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == target_id
    assert get_resp.json()["kind"] == "api"


@pytest.mark.asyncio
async def test_list_targets(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org C")
    for i in range(3):
        await client.post(
            f"/v1/orgs/{org_id}/targets",
            json={"name": f"target-{i}", "kind": "web"},
        )

    list_resp = await client.get(f"/v1/orgs/{org_id}/targets")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["cursor"] is None


@pytest.mark.asyncio
async def test_list_targets_pagination(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org Pag")
    for i in range(5):
        await client.post(
            f"/v1/orgs/{org_id}/targets",
            json={"name": f"pag-{i}", "kind": "api"},
        )

    page1 = await client.get(f"/v1/orgs/{org_id}/targets?limit=3")
    assert page1.status_code == 200
    d1 = page1.json()
    assert len(d1["items"]) == 3
    assert d1["total"] == 5
    assert d1["cursor"] is not None


@pytest.mark.asyncio
async def test_list_targets_pagination_walks_all_pages(client: AsyncClient) -> None:
    """Walking pages via the cursor must yield every row exactly once.

    Regression: cursor used Target.id while ordering by created_at, so the
    `id > after` filter skipped/duplicated rows under random UUID ids.
    """
    org_id = await _create_org(client, "Org PagWalk")
    created: set[str] = set()
    for i in range(7):
        r = await client.post(
            f"/v1/orgs/{org_id}/targets",
            json={"name": f"walk-{i}", "kind": "api"},
        )
        created.add(r.json()["id"])

    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):  # safety bound
        url = f"/v1/orgs/{org_id}/targets?limit=2"
        if cursor is not None:
            url += f"&after={cursor}"
        resp = await client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        seen.extend(item["id"] for item in data["items"])
        cursor = data["cursor"]
        if cursor is None:
            break

    assert len(seen) == len(set(seen)), "pages overlap — duplicate rows returned"
    assert set(seen) == created, "cursor pagination dropped or skipped rows"


@pytest.mark.asyncio
async def test_update_target(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org D")
    create_resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "old-name", "kind": "web"},
    )
    target_id = create_resp.json()["id"]

    patch_resp = await client.patch(
        f"/v1/targets/{target_id}",
        json={"name": "new-name", "base_url": "https://new.example.com"},
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["name"] == "new-name"
    assert data["base_url"] == "https://new.example.com"
    assert data["kind"] == "web"  # unchanged


@pytest.mark.asyncio
async def test_delete_target_soft(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org E")
    create_resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "to-delete", "kind": "mobile"},
    )
    target_id = create_resp.json()["id"]

    del_resp = await client.delete(f"/v1/targets/{target_id}")
    assert del_resp.status_code == 204

    # Soft delete — GET must return 404
    get_resp = await client.get(f"/v1/targets/{target_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_deleted_target_excluded_from_list(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Org F")
    await client.post(f"/v1/orgs/{org_id}/targets", json={"name": "keep", "kind": "web"})
    r2 = await client.post(
        f"/v1/orgs/{org_id}/targets", json={"name": "delete-me", "kind": "api"}
    )
    await client.delete(f"/v1/targets/{r2.json()['id']}")

    list_resp = await client.get(f"/v1/orgs/{org_id}/targets")
    data = list_resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "keep"


@pytest.mark.asyncio
async def test_get_nonexistent_target_404(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/targets/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Role enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_viewer_cannot_create_target(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    """A 'member' role must not be able to create targets."""
    org_id = await _create_org(client, "Viewer Org")
    org_uuid = uuid.UUID(org_id)

    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == org_uuid, OrgMember.user_id == dev_user_id)
        .values(role="member")
    )
    await db_session.commit()

    resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "blocked", "kind": "web"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_update_target(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Viewer Org Update")
    org_uuid = uuid.UUID(org_id)

    create_resp = await client.post(
        f"/v1/orgs/{org_id}/targets", json={"name": "target", "kind": "web"}
    )
    target_id = create_resp.json()["id"]

    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == org_uuid, OrgMember.user_id == dev_user_id)
        .values(role="member")
    )
    await db_session.commit()

    resp = await client.patch(f"/v1/targets/{target_id}", json={"name": "blocked"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_delete_target(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Viewer Org Delete")
    org_uuid = uuid.UUID(org_id)

    create_resp = await client.post(
        f"/v1/orgs/{org_id}/targets", json={"name": "target", "kind": "api"}
    )
    target_id = create_resp.json()["id"]

    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == org_uuid, OrgMember.user_id == dev_user_id)
        .values(role="member")
    )
    await db_session.commit()

    resp = await client.delete(f"/v1/targets/{target_id}")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RunnerDispatcher routing tests (unit — no HTTP, no Cloud Tasks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_routes_by_product_docker_mode(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatcher returns 'docker' in docker mode and invokes docker dispatch."""
    monkeypatch.setenv("RUN_MODE", "docker")
    from testlyn_api.config import get_settings

    get_settings.cache_clear()

    await _seed_runner_registry(db_session)

    dispatched_calls: list[str] = []

    async def _fake_dispatch_docker(self, run_id: uuid.UUID) -> None:  # type: ignore[misc]
        dispatched_calls.append(str(run_id))

    from testlyn_api.core import runner_dispatcher

    monkeypatch.setattr(
        runner_dispatcher.RunnerDispatcher,
        "_dispatch_docker",
        _fake_dispatch_docker,
    )

    dispatcher = runner_dispatcher.RunnerDispatcher()
    run_id = uuid.uuid4()

    result = await dispatcher.dispatch(
        test_run_id=run_id, product="load", session=db_session
    )

    assert result == "docker"
    assert str(run_id) in dispatched_calls

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dispatcher_routes_functional_product_docker_mode(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dispatcher accepts 'functional' product and delegates to docker dispatch."""
    monkeypatch.setenv("RUN_MODE", "docker")
    from testlyn_api.config import get_settings

    get_settings.cache_clear()

    await _seed_runner_registry(db_session)

    called: list[str] = []

    async def _fake_dispatch_docker(self, run_id: uuid.UUID) -> None:  # type: ignore[misc]
        called.append(str(run_id))

    from testlyn_api.core import runner_dispatcher

    monkeypatch.setattr(
        runner_dispatcher.RunnerDispatcher,
        "_dispatch_docker",
        _fake_dispatch_docker,
    )

    dispatcher = runner_dispatcher.RunnerDispatcher()
    run_id = uuid.uuid4()
    result = await dispatcher.dispatch(
        test_run_id=run_id, product="functional", session=db_session
    )
    assert result == "docker"
    assert str(run_id) in called

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_dispatcher_unknown_product_still_dispatches(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unknown product has no registry row but dispatch still proceeds (image_uri=None)."""
    monkeypatch.setenv("RUN_MODE", "docker")
    from testlyn_api.config import get_settings

    get_settings.cache_clear()

    called: list[bool] = []

    async def _fake_dispatch_docker(self, run_id: uuid.UUID) -> None:  # type: ignore[misc]
        called.append(True)

    from testlyn_api.core import runner_dispatcher

    monkeypatch.setattr(
        runner_dispatcher.RunnerDispatcher,
        "_dispatch_docker",
        _fake_dispatch_docker,
    )

    dispatcher = runner_dispatcher.RunnerDispatcher()
    result = await dispatcher.dispatch(
        test_run_id=uuid.uuid4(), product="unknown-product", session=db_session
    )
    assert result == "docker"
    assert called

    get_settings.cache_clear()
