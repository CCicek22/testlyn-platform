"""
GraphQL endpoint tests — /v1/graphql.

Uses the same DEV_AUTH_BYPASS + SQLite-in-memory setup as all other tests.
Strawberry is imported lazily so the test module doesn't fail if the dep is
missing from the dev venv (CI installs full deps; local `uv sync` should too).
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _gql(client: AsyncClient, query: str, variables: dict | None = None) -> dict:
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = await client.post("/v1/graphql", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "errors" not in body, body.get("errors")
    return body["data"]


# ---------------------------------------------------------------------------
# me query
# ---------------------------------------------------------------------------


async def test_graphql_me(client: AsyncClient) -> None:
    data = await _gql(client, "{ me { id email } }")
    assert data["me"]["email"] == "dev@testlyn.io"
    assert data["me"]["id"]


# ---------------------------------------------------------------------------
# org query
# ---------------------------------------------------------------------------


async def test_graphql_org_not_found(client: AsyncClient) -> None:
    import uuid

    resp = await client.post(
        "/v1/graphql",
        json={"query": f'{{ org(id: "{uuid.uuid4()}") {{ id name }} }}'},
    )
    assert resp.status_code == 200
    body = resp.json()
    # null is valid for optional field
    assert body["data"]["org"] is None


async def test_graphql_org_found(
    client: AsyncClient, db_session: AsyncSession, dev_user_id
) -> None:
    import uuid

    from testlyn_api.models.org import Organization, OrgMember

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="GQL Org", slug="gql-org")
    db_session.add(org)
    await db_session.flush()
    # Caller must be a member to read the org (tenant isolation).
    db_session.add(OrgMember(org_id=org_id, user_id=dev_user_id, role="viewer"))
    await db_session.commit()

    data = await _gql(client, f'{{ org(id: "{org_id}") {{ id name slug }} }}')
    assert data["org"]["name"] == "GQL Org"
    assert data["org"]["slug"] == "gql-org"


async def test_graphql_org_cross_tenant_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A user who is not a member of org B cannot read it via GraphQL → null."""
    import uuid

    from testlyn_api.models.org import Organization

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="Other Tenant", slug="other-tenant-org")
    db_session.add(org)
    await db_session.commit()  # dev user is NOT a member

    data = await _gql(client, f'{{ org(id: "{org_id}") {{ id name }} }}')
    assert data["org"] is None


# ---------------------------------------------------------------------------
# tests query
# ---------------------------------------------------------------------------


async def test_graphql_tests_empty(client: AsyncClient) -> None:
    import uuid

    data = await _gql(client, f'{{ tests(projectId: "{uuid.uuid4()}") {{ id }} }}')
    assert data["tests"] == []


async def test_graphql_tests_returns_rows(
    client: AsyncClient, db_session: AsyncSession, dev_user_id
) -> None:
    import uuid

    from testlyn_api.models.org import Organization, OrgMember
    from testlyn_api.models.project import Project
    from testlyn_api.models.test import Test

    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    org = Organization(id=org_id, name="Org", slug="org-gql-tests")
    db_session.add(org)
    await db_session.flush()
    # Caller must be a member of the owning org to list tests.
    db_session.add(OrgMember(org_id=org_id, user_id=dev_user_id, role="viewer"))
    await db_session.flush()
    project = Project(id=project_id, name="Proj", slug="proj-gql-tests", org_id=org_id)
    db_session.add(project)
    await db_session.flush()
    t = Test(
        id=uuid.uuid4(),
        name="My Load Test",
        product="load",
        project_id=project_id,
        config={},
    )
    db_session.add(t)
    await db_session.commit()

    data = await _gql(client, f'{{ tests(projectId: "{project_id}") {{ id name product }} }}')
    assert len(data["tests"]) == 1
    assert data["tests"][0]["name"] == "My Load Test"
    assert data["tests"][0]["product"] == "load"


async def test_graphql_tests_cross_tenant_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Tests under a project in another org are not visible → empty list."""
    import uuid

    from testlyn_api.models.org import Organization
    from testlyn_api.models.project import Project
    from testlyn_api.models.test import Test

    org_id = uuid.uuid4()
    project_id = uuid.uuid4()
    org = Organization(id=org_id, name="Other", slug="other-tenant-tests")
    db_session.add(org)
    await db_session.flush()
    project = Project(id=project_id, name="P", slug="proj-other-tenant", org_id=org_id)
    db_session.add(project)
    await db_session.flush()
    t = Test(
        id=uuid.uuid4(),
        name="Secret Test",
        product="load",
        project_id=project_id,
        config={},
    )
    db_session.add(t)
    await db_session.commit()  # dev user is NOT a member of this org

    data = await _gql(client, f'{{ tests(projectId: "{project_id}") {{ id name }} }}')
    assert data["tests"] == []


# ---------------------------------------------------------------------------
# runs query
# ---------------------------------------------------------------------------


async def test_graphql_runs_empty(client: AsyncClient) -> None:
    import uuid

    data = await _gql(client, f'{{ runs(testId: "{uuid.uuid4()}") {{ id }} }}')
    assert data["runs"] == []


async def test_graphql_runs_returns_rows_for_member(
    client: AsyncClient, db_session: AsyncSession, dev_user_id
) -> None:
    """Member can read runs; status maps from TestRun.state (regression for r.status)."""
    import uuid

    from testlyn_api.models.org import Organization, OrgMember
    from testlyn_api.models.project import Project
    from testlyn_api.models.test import Test
    from testlyn_api.models.test_run import TestRun

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="MyOrg", slug="myorg-runs")
    db_session.add(org)
    await db_session.flush()
    db_session.add(OrgMember(org_id=org_id, user_id=dev_user_id, role="member"))
    await db_session.flush()
    project = Project(id=uuid.uuid4(), name="P", slug="proj-runs", org_id=org_id)
    db_session.add(project)
    await db_session.flush()
    t = Test(id=uuid.uuid4(), name="T", product="load", project_id=project.id, config={})
    db_session.add(t)
    await db_session.flush()
    run = TestRun(id=uuid.uuid4(), test_id=t.id, product="load", state="completed")
    db_session.add(run)
    await db_session.commit()

    data = await _gql(client, f'{{ runs(testId: "{t.id}") {{ id status product }} }}')
    assert len(data["runs"]) == 1
    assert data["runs"][0]["status"] == "completed"
    assert data["runs"][0]["product"] == "load"


async def test_graphql_runs_cross_tenant_denied(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Runs for a test in another org are not visible → empty list."""
    import uuid

    from testlyn_api.models.org import Organization
    from testlyn_api.models.project import Project
    from testlyn_api.models.test import Test
    from testlyn_api.models.test_run import TestRun

    org_id = uuid.uuid4()
    org = Organization(id=org_id, name="OtherRuns", slug="other-tenant-runs")
    db_session.add(org)
    await db_session.flush()
    project = Project(id=uuid.uuid4(), name="P", slug="proj-other-runs", org_id=org_id)
    db_session.add(project)
    await db_session.flush()
    t = Test(id=uuid.uuid4(), name="T", product="load", project_id=project.id, config={})
    db_session.add(t)
    await db_session.flush()
    run = TestRun(id=uuid.uuid4(), test_id=t.id, product="load", state="completed")
    db_session.add(run)
    await db_session.commit()  # dev user is NOT a member of this org

    data = await _gql(client, f'{{ runs(testId: "{t.id}") {{ id status }} }}')
    assert data["runs"] == []


# ---------------------------------------------------------------------------
# plugins query
# ---------------------------------------------------------------------------


async def test_graphql_plugins_empty(client: AsyncClient) -> None:
    data = await _gql(client, "{ plugins { slug kind } }")
    assert data["plugins"] == []


async def test_graphql_plugins_with_data(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid

    from testlyn_api.models.plugin import Plugin

    p = Plugin(
        id=uuid.uuid4(),
        slug="slack-notifier",
        kind="integration",
        name="Slack Notifier",
        description="Post results to Slack",
        author="community",
        version="0.1.0",
    )
    db_session.add(p)
    await db_session.commit()

    data = await _gql(client, "{ plugins { slug kind name installCount } }")
    assert len(data["plugins"]) == 1
    assert data["plugins"][0]["slug"] == "slack-notifier"
    assert data["plugins"][0]["kind"] == "integration"


async def test_graphql_plugins_filter_by_kind(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid

    from testlyn_api.models.plugin import Plugin

    runner = Plugin(
        id=uuid.uuid4(),
        slug="my-runner",
        kind="runner",
        name="My Runner",
        description="A runner",
        author="community",
        version="0.1.0",
    )
    integration = Plugin(
        id=uuid.uuid4(),
        slug="my-integration",
        kind="integration",
        name="My Integration",
        description="An integration",
        author="community",
        version="0.1.0",
    )
    db_session.add_all([runner, integration])
    await db_session.commit()

    data = await _gql(client, '{ plugins(kind: "runner") { slug kind } }')
    assert len(data["plugins"]) == 1
    assert data["plugins"][0]["kind"] == "runner"


# ---------------------------------------------------------------------------
# scenarios query
# ---------------------------------------------------------------------------


async def test_graphql_scenarios_empty(client: AsyncClient) -> None:
    data = await _gql(client, "{ scenarios { slug } }")
    assert data["scenarios"] == []


async def test_graphql_scenarios_with_data(client: AsyncClient, db_session: AsyncSession) -> None:
    import uuid

    from testlyn_api.models.scenario import Scenario

    s = Scenario(
        id=uuid.uuid4(),
        slug="k6-ramp-spike",
        name="Ramp + Spike",
        description="Three-stage ramp script",
        product="load",
        author="Testlyn",
    )
    db_session.add(s)
    await db_session.commit()

    data = await _gql(client, "{ scenarios { slug name product priceCents } }")
    assert len(data["scenarios"]) == 1
    assert data["scenarios"][0]["slug"] == "k6-ramp-spike"
    assert data["scenarios"][0]["product"] == "load"
    assert data["scenarios"][0]["priceCents"] == 0


async def test_graphql_scenarios_filter_by_product(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    import uuid

    from testlyn_api.models.scenario import Scenario

    load_s = Scenario(
        id=uuid.uuid4(),
        slug="load-scenario",
        name="Load Scenario",
        description="A load scenario",
        product="load",
        author="Testlyn",
    )
    db_session.add(load_s)
    await db_session.commit()

    data = await _gql(client, '{ scenarios(product: "load") { slug product } }')
    assert all(s["product"] == "load" for s in data["scenarios"])

    data2 = await _gql(client, '{ scenarios(product: "functional") { slug } }')
    assert data2["scenarios"] == []
