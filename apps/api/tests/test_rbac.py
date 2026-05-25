"""RBAC permission matrix tests.

Covers:
- viewer cannot trigger test runs
- non-member gets 403
- member vs admin vs owner distinctions for target/audit mutations
- project role override takes precedence over org role
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.models.org import OrgMember
from testlyn_api.models.project_role_override import ProjectRoleOverride

# ── Helpers ────────────────────────────────────────────────────────────────────


async def _create_org(client: AsyncClient, name: str = "Rbac Org") -> str:
    resp = await client.post("/v1/orgs", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _set_role(db_session: AsyncSession, org_id: str, user_id: uuid.UUID, role: str) -> None:
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == user_id)
        .values(role=role)
    )
    await db_session.commit()


async def _create_project(client: AsyncClient, org_id: str) -> str:
    resp = await client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "RbacProj", "slug": f"rbac-{uuid.uuid4().hex[:6]}"},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_test(client: AsyncClient, project_id: str) -> str:
    resp = await client.post(
        f"/v1/projects/{project_id}/tests",
        json={
            "name": "RbacTest",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 10},
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ── Non-member ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_non_member_cannot_create_target(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """User with no org membership gets 403 on target creation."""
    # Create an org but then remove the auto-added membership
    org_id = await _create_org(client, "NonMemberOrg")
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id)
        .values(role="viewer")  # demote first so we can test non-member separately
    )
    # Delete membership entirely
    from sqlalchemy import delete

    await db_session.execute(
        delete(OrgMember).where(
            OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id
        )
    )
    await db_session.commit()

    resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "blocked", "kind": "web", "base_url": "https://blocked.example.com"},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"].lower()
    # targets.py uses _assert_org_owner_or_admin which returns "Insufficient role"
    # for any non-admin (including non-members); either message is acceptable
    assert "member" in detail or "insufficient" in detail or "role" in detail


# ── Viewer cannot trigger runs ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_cannot_trigger_run(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch,
) -> None:
    """viewer role must get 403 on POST /v1/tests/{test_id}/runs."""
    from testlyn_api.core import tasks

    async def _noop(_): pass
    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id = await _create_org(client, "ViewerRunOrg")
    proj_id = await _create_project(client, org_id)
    test_id = await _create_test(client, proj_id)

    await _set_role(db_session, org_id, dev_user_id, "viewer")

    resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert resp.status_code == 403
    assert "viewer" in resp.json()["detail"].lower() or "member" in resp.json()["detail"].lower()


# ── Member can trigger runs ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_member_can_trigger_run(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch,
) -> None:
    """member role must succeed on POST /v1/tests/{test_id}/runs."""
    from testlyn_api.core import tasks

    async def _noop(_): pass
    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id = await _create_org(client, "MemberRunOrg")
    proj_id = await _create_project(client, org_id)
    test_id = await _create_test(client, proj_id)

    # Default role after org creation is "owner" (dev user created it); set to member
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert resp.status_code == 201


# ── Viewer can read ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_can_read_org(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "ViewerReadOrg")
    await _set_role(db_session, org_id, dev_user_id, "viewer")

    resp = await client.get(f"/v1/orgs/{org_id}")
    assert resp.status_code == 200


# ── Member cannot create target (admin-only) ───────────────────────────────────


@pytest.mark.asyncio
async def test_member_cannot_create_target(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "MemberTargetOrg")
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "should-fail", "kind": "api"},
    )
    assert resp.status_code == 403


# ── Admin can create target ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_can_create_target(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "AdminTargetOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")

    resp = await client.post(
        f"/v1/orgs/{org_id}/targets",
        json={"name": "admin-target", "kind": "api"},
    )
    assert resp.status_code == 201


# ── Audit log requires admin+ ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_member_cannot_read_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "AuditMemberOrg")
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_read_audit_log(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "AuditAdminOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")

    resp = await client.get(f"/v1/orgs/{org_id}/audit-log")
    assert resp.status_code == 200


# ── Sink CRUD requires owner ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_admin_cannot_create_sink(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkAdminOrg")
    await _set_role(db_session, org_id, dev_user_id, "admin")

    resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={"kind": "generic_https", "config": {"url": "https://example.com/sink"}},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_create_sink(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    org_id = await _create_org(client, "SinkOwnerOrg")
    # org creator is already owner — no role change needed

    resp = await client.post(
        f"/v1/orgs/{org_id}/audit-sinks",
        json={"kind": "generic_https", "config": {"url": "https://hooks.example.com"}},
    )
    assert resp.status_code == 201


# ── Project role override takes precedence ─────────────────────────────────────


@pytest.mark.asyncio
async def test_project_override_elevates_viewer_to_member(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch,
) -> None:
    """Org-level viewer + project-level member override → can write test in that project."""
    org_id = await _create_org(client, "OverrideOrg")
    proj_id = await _create_project(client, org_id)

    # Demote to viewer at org level
    await _set_role(db_session, org_id, dev_user_id, "viewer")

    # Verify viewer cannot create test (member-only)
    resp_no_override = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "ShouldFail",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 10},
        },
    )
    assert resp_no_override.status_code == 403

    # Add project-level member override
    override = ProjectRoleOverride(
        project_id=uuid.UUID(proj_id),
        user_id=dev_user_id,
        role="member",
    )
    db_session.add(override)
    await db_session.commit()

    # Now viewer with project override can create test
    resp_with_override = await client.post(
        f"/v1/projects/{proj_id}/tests",
        json={
            "name": "ShouldSucceed",
            "script_inline": "export default function() {}",
            "config": {"vus": 1, "duration_seconds": 10},
        },
    )
    assert resp_with_override.status_code == 201


# ── Viewer cannot create project (member-only) ─────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_cannot_create_project(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """viewer role must get 403 on POST /v1/orgs/{org_id}/projects (write:project=member)."""
    org_id = await _create_org(client, "ViewerProjOrg")
    await _set_role(db_session, org_id, dev_user_id, "viewer")

    resp = await client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "ShouldFail", "slug": "should-fail"},
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"].lower()
    assert "viewer" in detail or "member" in detail


@pytest.mark.asyncio
async def test_member_can_create_project(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
) -> None:
    """member role must succeed on POST /v1/orgs/{org_id}/projects."""
    org_id = await _create_org(client, "MemberProjOrg")
    await _set_role(db_session, org_id, dev_user_id, "member")

    resp = await client.post(
        f"/v1/orgs/{org_id}/projects",
        json={"name": "Ok Project", "slug": "ok-project"},
    )
    assert resp.status_code == 201


# ── Schedule listing enforces org membership ───────────────────────────────────


@pytest.mark.asyncio
async def test_list_schedules_cross_org_denied(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Listing schedules for an org the caller does not belong to → 403."""
    from testlyn_api.models.org import Organization

    other_org_id = uuid.uuid4()
    other = Organization(
        id=other_org_id,
        name="OtherSchedOrg",
        slug=f"other-sched-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(other)
    await db_session.commit()  # dev user is NOT a member of this org

    resp = await client.get(f"/v1/schedules?org_id={other_org_id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_schedules_own_org_allowed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
) -> None:
    """Caller who is a member of the org can list its schedules (200)."""
    from testlyn_api.routers import schedules as sched_router

    async def _empty(_org_id: str):
        return []

    monkeypatch.setattr(sched_router.svc, "list_schedules", _empty)

    org_id = await _create_org(client, "OwnSchedOrg")  # dev user is owner

    resp = await client.get(f"/v1/schedules?org_id={org_id}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_schedules_invalid_org_id_400(
    client: AsyncClient,
) -> None:
    """Non-UUID org_id is rejected with 400 before any service call."""
    resp = await client.get("/v1/schedules?org_id=not-a-uuid")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_project_override_restricts_admin_to_viewer(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch,
) -> None:
    """Org-level admin + project-level viewer override → cannot trigger run in that project."""
    from testlyn_api.core import tasks

    async def _noop(_): pass
    monkeypatch.setattr(tasks, "enqueue_run", _noop)

    org_id = await _create_org(client, "RestrictOrg")
    proj_id = await _create_project(client, org_id)
    test_id = await _create_test(client, proj_id)

    # org owner can run (default) — set admin
    await _set_role(db_session, org_id, dev_user_id, "admin")

    # Add project-level viewer override (restricts to read-only for this project)
    override = ProjectRoleOverride(
        project_id=uuid.UUID(proj_id),
        user_id=dev_user_id,
        role="viewer",
    )
    db_session.add(override)
    await db_session.commit()

    resp = await client.post(f"/v1/tests/{test_id}/runs", json={})
    assert resp.status_code == 403
