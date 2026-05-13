"""
Strawberry GraphQL schema for Testlyn API.

Wraps existing REST resolvers — no business logic lives here.
Auth is enforced via the Strawberry context (populated by the router).
All resolvers delegate to the same async SQLAlchemy session used by REST.
"""
from __future__ import annotations

import uuid
from typing import Optional

import strawberry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.auth import CurrentUser

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
    async def me(self, info: strawberry.types.Info) -> Optional[GQLUser]:
        user: CurrentUser = info.context["user"]
        return GQLUser(id=strawberry.ID(str(user.id)), email=user.email)

    @strawberry.field
    async def org(
        self, info: strawberry.types.Info, id: strawberry.ID
    ) -> Optional[GQLOrg]:
        from testlyn_api.models.org import Organization

        session: AsyncSession = info.context["session"]
        result = await session.execute(
            select(Organization).where(Organization.id == uuid.UUID(str(id)))
        )
        row = result.scalar_one_or_none()
        if row is None:
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
        from testlyn_api.models.test import Test

        session: AsyncSession = info.context["session"]
        result = await session.execute(
            select(Test).where(Test.project_id == uuid.UUID(str(project_id)))
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
        from testlyn_api.models.test_run import TestRun

        session: AsyncSession = info.context["session"]
        result = await session.execute(
            select(TestRun)
            .where(TestRun.test_id == uuid.UUID(str(test_id)))
            .order_by(TestRun.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            GQLRun(
                id=strawberry.ID(str(r.id)),
                test_id=strawberry.ID(str(r.test_id)),
                status=r.status,
                product=r.product,
            )
            for r in rows
        ]

    @strawberry.field
    async def plugins(
        self, info: strawberry.types.Info, kind: Optional[str] = None
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
        self, info: strawberry.types.Info, product: Optional[str] = None
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
