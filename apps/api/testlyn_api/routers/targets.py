from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select

from testlyn_api.deps import AuditDep, CurrentUserDep, SessionDep
from testlyn_api.models.org import Organization, OrgMember
from testlyn_api.models.target import Target
from testlyn_api.schemas.target import TargetCreate, TargetListOut, TargetOut, TargetUpdate

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["targets"])

_PAGE_SIZE = 20


async def _assert_org_member(org_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep) -> None:
    result = await session.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member")


async def _assert_org_owner_or_admin(
    org_id: uuid.UUID, user_id: uuid.UUID, session: SessionDep
) -> None:
    result = await session.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user_id,
            OrgMember.role.in_(["owner", "admin"]),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role — owner or admin required",
        )


async def _get_org_or_404(org_id: uuid.UUID, session: SessionDep) -> Organization:
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def _get_target_or_404(target_id: uuid.UUID, session: SessionDep) -> Target:
    result = await session.execute(
        select(Target).where(Target.id == target_id, Target.deleted_at.is_(None))
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
    return target


@router.get("/orgs/{org_id}/targets", response_model=TargetListOut)
async def list_targets(
    org_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=_PAGE_SIZE, ge=1, le=100),
    after: uuid.UUID | None = Query(default=None),  # noqa: B008
) -> TargetListOut:
    await _get_org_or_404(org_id, session)
    await _assert_org_member(org_id, current_user.id, session)

    base_q = select(Target).where(Target.org_id == org_id, Target.deleted_at.is_(None))

    count_result = await session.execute(
        select(func.count()).select_from(base_q.subquery())
    )
    total: int = count_result.scalar_one()

    items_q = base_q.order_by(Target.created_at.asc(), Target.id.asc()).limit(limit + 1)
    if after is not None:
        # Keyset pagination on the SAME tuple we order by — (created_at ASC,
        # id ASC). Filtering on Target.id alone skips/duplicates rows because the
        # id is a random uuid4 unrelated to created_at order. Reference the
        # cursor row's created_at via a correlated scalar subquery (rather than a
        # Python round-trip) so the comparison stays column-to-column in the DB
        # and isn't broken by datetime serialization differences across backends.
        cursor_exists = await session.scalar(select(Target.id).where(Target.id == after))
        if cursor_exists is not None:
            cursor_created_at = (
                select(Target.created_at).where(Target.id == after).scalar_subquery()
            )
            items_q = items_q.where(
                or_(
                    Target.created_at > cursor_created_at,
                    and_(
                        Target.created_at == cursor_created_at,
                        Target.id > after,
                    ),
                )
            )

    rows = (await session.execute(items_q)).scalars().all()

    cursor: uuid.UUID | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        cursor = rows[-1].id

    return TargetListOut(
        items=[TargetOut.model_validate(r) for r in rows],
        total=total,
        cursor=cursor,
    )


@router.post(
    "/orgs/{org_id}/targets",
    response_model=TargetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_target(
    org_id: uuid.UUID,
    body: TargetCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
    audit: AuditDep,
) -> TargetOut:
    await _get_org_or_404(org_id, session)
    await _assert_org_owner_or_admin(org_id, current_user.id, session)
    audit.set_org(org_id)

    target = Target(
        org_id=org_id,
        name=body.name,
        kind=body.kind,
        base_url=body.base_url,
        auth_config=body.auth_config,
    )
    session.add(target)
    await session.flush()
    await session.commit()
    await session.refresh(target)

    await audit.write(
        action="target.created",
        resource_type="target",
        resource_id=target.id,
        after={"name": target.name, "kind": target.kind, "org_id": str(org_id)},
        org_id=org_id,
    )
    await session.commit()

    log.info("target.created", target_id=str(target.id), org_id=str(org_id))
    return TargetOut.model_validate(target)


@router.get("/targets/{target_id}", response_model=TargetOut)
async def get_target(
    target_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> TargetOut:
    target = await _get_target_or_404(target_id, session)
    await _assert_org_member(target.org_id, current_user.id, session)
    return TargetOut.model_validate(target)


@router.patch("/targets/{target_id}", response_model=TargetOut)
async def update_target(
    target_id: uuid.UUID,
    body: TargetUpdate,
    current_user: CurrentUserDep,
    session: SessionDep,
    audit: AuditDep,
) -> TargetOut:
    target = await _get_target_or_404(target_id, session)
    await _assert_org_owner_or_admin(target.org_id, current_user.id, session)
    audit.set_org(target.org_id)

    before = {"name": target.name, "kind": target.kind, "base_url": target.base_url}

    if body.name is not None:
        target.name = body.name
    if body.kind is not None:
        target.kind = body.kind
    if body.base_url is not None:
        target.base_url = body.base_url
    if body.auth_config is not None:
        target.auth_config = body.auth_config
    target.updated_at = datetime.now(tz=UTC)

    await session.flush()
    await session.commit()
    await session.refresh(target)

    await audit.write(
        action="target.updated",
        resource_type="target",
        resource_id=target.id,
        before=before,
        after={"name": target.name, "kind": target.kind, "base_url": target.base_url},
        org_id=target.org_id,
    )
    await session.commit()

    log.info("target.updated", target_id=str(target.id))
    return TargetOut.model_validate(target)


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(
    target_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
    audit: AuditDep,
) -> None:
    target = await _get_target_or_404(target_id, session)
    await _assert_org_owner_or_admin(target.org_id, current_user.id, session)
    audit.set_org(target.org_id)

    target.deleted_at = datetime.now(tz=UTC)
    await session.flush()
    await session.commit()

    await audit.write(
        action="target.deleted",
        resource_type="target",
        resource_id=target.id,
        org_id=target.org_id,
    )
    await session.commit()

    log.info("target.deleted", target_id=str(target.id))
