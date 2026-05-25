"""
Strawberry GraphQL schema for Testlyn API.

Wraps existing REST resolvers — no business logic lives here.
Auth is enforced via the Strawberry context (populated by the router).
All resolvers delegate to the same async SQLAlchemy session used by REST.
"""
from __future__ import annotations

import uuid

import strawberry
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.auth import CurrentUser
from testlyn_api.core.permissions import _enforce_perm

# ---------------------------------------------------------------------------
# GraphQL types
# ---------------------------------------------------------------------------


@strawberry.type
class GQLUser:
    id: strawberry.ID
    email: str


@strawberry.type
class GQLOrg:
    id: strawberry.ID
    name: str
    slug: str


@strawberry.type
class GQLTest:
    id: strawberry.ID
    name: str
    product: str
    project_id: strawberry.ID


@strawberry.type
class GQLRun:
    id: strawberry.ID
    test_id: strawberry.ID
    status: str
    product: str


@strawberry.type
class GQLPlugin:
    id: strawberry.ID
    slug: str
    kind: str
    name: str
    description: str
    author: str
    version: str
    install_count: int


@strawberry.type
class GQLScenario:
    id: strawberry.ID
    slug: str
    name: str
    description: str
    product: str
    price_cents: int
    author: str


# ---------------------------------------------------------------------------
# Strawberry context
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    @strawberry.field
    async def me(self, info: strawberry.types.Info) -> GQLUser | None:
        user: CurrentUser = info.context["user"]
        return GQLUser(id=strawberry.ID(str(user.id)), email=user.email)

    @strawberry.field
    async def org(
        self, info: strawberry.types.Info, id: strawberry.ID
    ) -> GQLOrg | None:
        from testlyn_api.models.org import Organization

        session: AsyncSession = info.context["session"]
        user: CurrentUser = info.context["user"]
        result = await session.execute(
            select(Organization).where(Organization.id == uuid.UUID(str(id)))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        # Tenant isolation: caller must be able to read this org. Return null
        # (not an error) on failure so we don't leak org existence.
        try:
            await _enforce_perm(
                "read", "org", user_id=user.id, org_id=row.id, session=session
            )
        except HTTPException:
            return None
        return GQLOrg(
            id=strawberry.ID(str(row.id)),
            name=row.name,
            slug=row.slug,
        )

    @strawberry.field
    async def tests(
        self, info: strawberry.types.Info, project_id: strawberry.ID
    ) -> list[GQLTest]:
        from testlyn_api.models.project import Project
        from testlyn_api.models.test import Test

        session: AsyncSession = info.context["session"]
        user: CurrentUser = info.context["user"]
        pid = uuid.UUID(str(project_id))
        proj_result = await session.execute(
            select(Project).where(Project.id == pid)
        )
        project = proj_result.scalar_one_or_none()
        if project is None:
            return []
        # Tenant isolation: mirror REST list_tests (read:test). Empty on denial.
        try:
            await _enforce_perm(
                "read",
                "test",
                user_id=user.id,
                org_id=project.org_id,
                project_id=project.id,
                session=session,
            )
        except HTTPException:
            return []
        result = await session.execute(
            select(Test).where(Test.project_id == pid)
        )
        rows = result.scalars().all()
        return [
            GQLTest(
                id=strawberry.ID(str(r.id)),
                name=r.name,
                product=r.product,
                project_id=strawberry.ID(str(r.project_id)),
            )
            for r in rows
        ]

    @strawberry.field
    async def runs(
        self,
        info: strawberry.types.Info,
        test_id: strawberry.ID,
        limit: int = 20,
    ) -> list[GQLRun]:
        from testlyn_api.models.project import Project
        from testlyn_api.models.test import Test
        from testlyn_api.models.test_run import TestRun

        session: AsyncSession = info.context["session"]
        user: CurrentUser = info.context["user"]
        tid = uuid.UUID(str(test_id))
        # Traverse run → test → project → org to enforce RBAC (mirrors REST).
        test_result = await session.execute(select(Test).where(Test.id == tid))
        test = test_result.scalar_one_or_none()
        if test is None:
            return []
        proj_result = await session.execute(
            select(Project).where(Project.id == test.project_id)
        )
        project = proj_result.scalar_one_or_none()
        if project is None:
            return []
        try:
            await _enforce_perm(
                "read",
                "test_run",
                user_id=user.id,
                org_id=project.org_id,
                project_id=project.id,
                session=session,
            )
        except HTTPException:
            return []
        result = await session.execute(
            select(TestRun)
            .where(TestRun.test_id == tid)
            .order_by(TestRun.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            GQLRun(
                id=strawberry.ID(str(r.id)),
                test_id=strawberry.ID(str(r.test_id)),
                status=r.state,
                product=r.product,
            )
            for r in rows
        ]

    @strawberry.field
    async def plugins(
        self, info: strawberry.types.Info, kind: str | None = None
    ) -> list[GQLPlugin]:
        from testlyn_api.models.plugin import Plugin

        session: AsyncSession = info.context["session"]
        q = select(Plugin)
        if kind is not None:
            q = q.where(Plugin.kind == kind)
        result = await session.execute(q.order_by(Plugin.install_count.desc()))
        rows = result.scalars().all()
        return [
            GQLPlugin(
                id=strawberry.ID(str(r.id)),
                slug=r.slug,
                kind=r.kind,
                name=r.name,
                description=r.description,
                author=r.author,
                version=r.version,
                install_count=r.install_count,
            )
            for r in rows
        ]

    @strawberry.field
    async def scenarios(
        self, info: strawberry.types.Info, product: str | None = None
    ) -> list[GQLScenario]:
        from testlyn_api.models.scenario import Scenario

        session: AsyncSession = info.context["session"]
        q = select(Scenario)
        if product is not None:
            q = q.where(Scenario.product == product)
        result = await session.execute(q)
        rows = result.scalars().all()
        return [
            GQLScenario(
                id=strawberry.ID(str(r.id)),
                slug=r.slug,
                name=r.name,
                description=r.description,
                product=r.product,
                price_cents=r.price_cents,
                author=r.author,
            )
            for r in rows
        ]


schema = strawberry.Schema(query=Query)
