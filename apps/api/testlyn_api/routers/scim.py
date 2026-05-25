"""SCIM v2 provisioning endpoints.

Endpoints
---------
GET    /v2/scim/{org_id}/Users              — list users
POST   /v2/scim/{org_id}/Users              — create user
GET    /v2/scim/{org_id}/Users/{user_id}    — get user
PUT    /v2/scim/{org_id}/Users/{user_id}    — replace user
DELETE /v2/scim/{org_id}/Users/{user_id}    — delete user (removes membership)
GET    /v2/scim/{org_id}/Groups             — list groups (scaffold: empty)

Auth: Bearer token in Authorization header.  The presented token is compared
in constant time against the org's configured SCIM secret (SCIM_TOKENS_RAW,
sourced from Secret Manager).  Verification is bound to the {org_id} in the
path, so org A's token cannot act on org B.  Fails closed: an org with no
configured token rejects every request.  DEV_AUTH_BYPASS skips the check for
local/test runs only (forbidden when run_mode='cloud').

Note: These endpoints are intentionally on /v2/ (not /v1/) to match the
SCIM 2.0 spec URL convention and stay independent of the API rate-limiter
which only covers /v1/ routes.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

import structlog
from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from testlyn_api.config import get_settings
from testlyn_api.deps import SessionDep
from testlyn_api.services import scim as scim_svc

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v2/scim", tags=["scim"])

_SCIM_CONTENT_TYPE = "application/scim+json"


def _scim_response(content: dict, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=content, status_code=status_code, media_type=_SCIM_CONTENT_TYPE)


def _assert_scim_enabled() -> None:
    """Return 503 when SCIM provisioning is disabled for this deployment."""
    settings = get_settings()
    if not settings.scim_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SCIM provisioning is not enabled for this deployment",
        )


def _verify_bearer(authorization: str | None, org_id: uuid.UUID) -> None:
    """Verify the SCIM bearer token against the org's configured SCIM secret.

    The presented token is compared in constant time (``secrets.compare_digest``
    over SHA-256 digests, so token length is not leaked) against the per-org
    secret configured in SCIM_TOKENS_RAW.  Verification is bound to ``org_id``,
    so a token issued for one org cannot operate on another.  Fails closed: an
    org with no configured token rejects every request.  DEV_AUTH_BYPASS skips
    the check for local/test runs only (never reachable in cloud mode).
    """
    settings = get_settings()
    if settings.dev_auth_bypass:
        return  # test / local dev — skip

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required for SCIM",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty SCIM bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expected = settings.scim_tokens.get(str(org_id).lower())
    if not expected or not secrets.compare_digest(
        hashlib.sha256(token.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid SCIM bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/{org_id}/Users")
async def list_scim_users(
    org_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    authorization: str | None = Header(default=None),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
    count: int = Query(default=100, ge=1, le=1000),
    filter: str | None = Query(default=None),
) -> JSONResponse:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    data = await scim_svc.scim_list_users(
        session,
        org_id,
        _base_url(request),
        start_index=start_index,
        count=count,
        filter_str=filter,
    )
    return _scim_response(data)


@router.post("/{org_id}/Users", status_code=status.HTTP_201_CREATED)
async def create_scim_user(
    org_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    payload = await request.json()
    data = await scim_svc.scim_create_user(session, org_id, payload, _base_url(request))
    return _scim_response(data, status_code=status.HTTP_201_CREATED)


@router.get("/{org_id}/Users/{user_id}")
async def get_scim_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    data = await scim_svc.scim_get_user(session, org_id, user_id, _base_url(request))
    if data is None:
        return _scim_response(
            scim_svc.scim_error(404, "User not found"), status_code=404
        )
    return _scim_response(data)


@router.put("/{org_id}/Users/{user_id}")
async def replace_scim_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    payload = await request.json()
    data = await scim_svc.scim_replace_user(
        session, org_id, user_id, payload, _base_url(request)
    )
    if data is None:
        return _scim_response(
            scim_svc.scim_error(404, "User not found"), status_code=404
        )
    return _scim_response(data)


@router.delete("/{org_id}/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scim_user(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    session: SessionDep,
    authorization: str | None = Header(default=None),
) -> None:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    deleted = await scim_svc.scim_delete_user(session, org_id, user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")


# ---------------------------------------------------------------------------
# Groups (scaffold)
# ---------------------------------------------------------------------------


@router.get("/{org_id}/Groups")
async def list_scim_groups(
    org_id: uuid.UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    start_index: int = Query(default=1, ge=1, alias="startIndex"),
    count: int = Query(default=100, ge=1, le=1000),
) -> JSONResponse:
    _assert_scim_enabled()
    _verify_bearer(authorization, org_id)
    data = await scim_svc.scim_list_groups(org_id, _base_url(request), start_index, count)
    return _scim_response(data)
