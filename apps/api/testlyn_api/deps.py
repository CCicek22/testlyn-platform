from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.audit import AuditService, get_audit_service
from testlyn_api.core.auth import CurrentUser, get_current_user
from testlyn_api.core.db import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _resolve_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),  # noqa: B008
) -> CurrentUser:
    return await get_current_user(request=request, session=session)


CurrentUserDep = Annotated[CurrentUser, Depends(_resolve_current_user)]

AuditDep = Annotated[AuditService, Depends(get_audit_service)]
