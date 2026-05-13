"""
GraphQL router — mounts Strawberry schema at /v1/graphql.

Auth is identical to all REST routes: the existing `get_current_user`
dependency resolves the caller identity before the resolver runs.

Implementation note: `allow_queries_via_get=False` and `graphql_ide=None`
disable the GET route that Strawberry registers at startup. That GET route
triggers FastAPI dependency introspection which chokes on AsyncSession (a
non-Pydantic type). POST-only is sufficient for programmatic clients; GraphiQL
can be accessed via Apollo Studio or the Strawberry CLI if needed in dev.
"""
from __future__ import annotations

from fastapi import Depends, Request
from strawberry.fastapi import GraphQLRouter

from testlyn_api.core.auth import CurrentUser
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.graphql import schema


async def _get_context(
    request: Request,
    session: SessionDep,
    user: CurrentUserDep,
):
    return {"request": request, "session": session, "user": user}


graphql_router = GraphQLRouter(
    schema=schema,
    context_getter=_get_context,
    graphql_ide=None,
    allow_queries_via_get=False,
    prefix="/v1/graphql",
    tags=["graphql"],
)
