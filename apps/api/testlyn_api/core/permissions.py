"""RBAC permission matrix and FastAPI dependency.

Permission matrix
-----------------
Actions  : read | write | delete | run | manage_members | manage_billing
Resources: org | project | target | test | test_run | report | audit_log

Role hierarchy (ascending privilege):
  viewer < member < admin < owner

Each cell in the matrix is the *minimum* role required for (action, resource).
"""

import uuid

import structlog
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.org import OrgMember
from testlyn_api.models.project_role_override import ProjectRoleOverride

log = structlog.get_logger(__name__)

# ── Role ordering ──────────────────────────────────────────────────────────────

_ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
    "owner": 3,
}


def _rank(role: str) -> int:
    return _ROLE_RANK.get(role, -1)


# ── Permission matrix ─────────────────────────────────────────────────────────
# Format: {(action, resource_kind): minimum_required_role}

PERMISSION_MATRIX: dict[tuple[str, str], str] = {
    # ── org ───────────────────────────────────────────────────────────────────
    ("read", "org"): "viewer",
    ("write", "org"): "admin",
    ("delete", "org"): "owner",
    ("manage_members", "org"): "admin",
    ("manage_billing", "org"): "owner",
    # ── project ───────────────────────────────────────────────────────────────
    ("read", "project"): "viewer",
    ("write", "project"): "member",
    ("delete", "project"): "admin",
    # ── target ────────────────────────────────────────────────────────────────
    ("read", "target"): "viewer",
    ("write", "target"): "admin",
    ("delete", "target"): "admin",
    # ── test ──────────────────────────────────────────────────────────────────
    ("read", "test"): "viewer",
    ("write", "test"): "member",
    ("delete", "test"): "member",
    ("run", "test"): "member",  # viewer CANNOT trigger runs
    # ── test_run ──────────────────────────────────────────────────────────────
    ("read", "test_run"): "viewer",
    ("delete", "test_run"): "admin",
    # ── report ────────────────────────────────────────────────────────────────
    ("read", "report"): "viewer",
    ("write", "report"): "member",
    # ── audit_log ─────────────────────────────────────────────────────────────
    ("read", "audit_log"): "admin",
    ("write", "audit_log"): "owner",  # sinks CRUD
    ("delete", "audit_log"): "owner",
}


# ── Role resolution ───────────────────────────────────────────────────────────


async def _resolve_role(
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None,
    session: AsyncSession,
) -> str | None:
    """Return the effective role for (user, org[, project]).

    Project-level override takes precedence over org-level role when present.
    Returns None if the user is not a member of the org at all.
    """
    # 1. Org membership
    result = await session.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id, OrgMember.user_id == user_id
        )
    )
    member = result.scalar_one_or_none()
    if member is None:
        return None

    org_role = member.role

    # 2. Project override (if project_id provided)
    if project_id is not None:
        override_result = await session.execute(
            select(ProjectRoleOverride).where(
                ProjectRoleOverride.project_id == project_id,
                ProjectRoleOverride.user_id == user_id,
            )
        )
        override = override_result.scalar_one_or_none()
        if override is not None:
            return override.role

    return org_role


async def _enforce_perm(
    action: str,
    resource_kind: str,
    *,
    user_id: uuid.UUID,
    org_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    session: AsyncSession,
) -> None:
    """Resolve role and raise 403 if insufficient — call directly from route handlers."""
    required = PERMISSION_MATRIX.get((action, resource_kind))
    if required is None:
        return  # no matrix entry — allow

    role = await _resolve_role(
        user_id=user_id,
        org_id=org_id,
        project_id=project_id,
        session=session,
    )
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a member of this organisation",
        )
    if _rank(role) < _rank(required):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' insufficient — '{required}' required for {action}:{resource_kind}",
        )


def perm_dep(action: str, resource_kind: str, **kwargs: str) -> object:
    """Shorthand: ``Depends(fn)`` for use in ``dependencies=[...]`` on route decorators.

    Works around PEP-563 (from __future__ import annotations) by setting
    ``__annotations__`` explicitly so FastAPI can evaluate them at import time.
    """
    import fastapi

    async def _dep(request, session, current_user) -> None:  # type: ignore[no-untyped-def]
        required = PERMISSION_MATRIX.get((action, resource_kind))
        if required is None:
            return

        oid_raw = request.path_params.get(kwargs.get("org_id_param", "org_id"))
        if oid_raw is None:
            return

        org_id = uuid.UUID(str(oid_raw))
        pid: uuid.UUID | None = None
        pid_param = kwargs.get("project_id_param")
        if pid_param:
            pid_raw = request.path_params.get(pid_param)
            if pid_raw is not None:
                pid = uuid.UUID(str(pid_raw))

        role = await _resolve_role(
            user_id=current_user.id,
            org_id=org_id,
            project_id=pid,
            session=session,
        )

        if role is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this organisation")

        if _rank(role) < _rank(required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' insufficient — '{required}' required for {action}:{resource_kind}",
            )

    # Set annotations explicitly (not as strings) so FastAPI can resolve them
    # even when the module uses `from __future__ import annotations`.
    # Use _resolve_current_user (which wraps get_current_user with proper
    # session injection) instead of get_current_user directly.
    from testlyn_api.deps import CurrentUserDep, SessionDep

    _dep.__annotations__ = {
        "request": fastapi.Request,
        "session": SessionDep,
        "current_user": CurrentUserDep,
        "return": None,
    }
    _dep.__name__ = f"perm_{action}_{resource_kind}"
    return Depends(_dep)
