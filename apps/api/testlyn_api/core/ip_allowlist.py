"""IP allowlist middleware.

Reads the org's active CIDR entries from Postgres on every request that
carries an org_id claim. When the org has >=1 active entry the middleware
rejects requests from IPs outside those CIDRs with 403.

Off by default — no entries = no restriction (allow-all).

Trusted-proxy handling:
  Reads X-Forwarded-For and trusts the first IP in the chain (rightmost
  entry added by the load balancer in front of Cloud Run is the real client
  IP in GCP's default configuration). Configurable via TRUSTED_PROXY_DEPTH.

Performance:
  Allowlists are cached in-process with a 30 s TTL. Cache is keyed by org_id.
  For high-volume orgs this avoids per-request DB queries.
"""

from __future__ import annotations

import ipaddress
import time
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = structlog.get_logger(__name__)

_CACHE_TTL = 30.0  # seconds
_cache: dict[str, tuple[list[str], float]] = {}  # org_id -> ([cidr,...], expire_ts)


def _extract_client_ip(request: Request, trusted_depth: int = 1) -> str:
    """Return the real client IP honoring X-Forwarded-For depth."""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        parts = [p.strip() for p in xff.split(",")]
        # The entry at index -(trusted_depth) is the client IP added by the
        # outermost trusted proxy.
        idx = -(trusted_depth)
        try:
            return parts[idx]
        except IndexError:
            return parts[0]
    return request.client.host if request.client else "127.0.0.1"


def _ip_in_cidr_list(ip_str: str, cidrs: list[str]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


async def _extract_org_id(request: Request) -> str | None:
    """Extract org_id for allowlist keying.

    Security: never trusts an un-verified JWT payload. The Bearer token is
    verified via ``token_verify.verify_token`` (Firebase signature + expiry).
    The verified token only carries ``uid`` (no ``org_id`` claim), so the org is
    resolved from Postgres via ``org_context.resolve_org_and_plan`` (cached). This
    lets the allowlist engage on EVERY ``/v1/`` route, not just ``/v1/orgs/{id}``.

    Falls back to path-based extraction (``/v1/orgs/{org_id}/...``) when no
    token is present — the org_id in the URL is still attacker-controlled
    here, but the allowlist only restricts the request *more* (never opens
    new access), so a forged path id can at most lock the caller out of an
    org they have no real access to.
    """
    from testlyn_api.core.org_context import OrgContextError, resolve_org_and_plan
    from testlyn_api.core.token_verify import extract_bearer, verify_token

    token = extract_bearer(request.headers.get("Authorization", ""))
    if token is not None:
        claims = await verify_token(token)
        if claims is not None:
            uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
            if uid:
                try:
                    org_id, _plan = await resolve_org_and_plan(str(uid))
                except OrgContextError as exc:
                    log.error("ip_allowlist._extract_org_id.db_error_fail_closed", uid=uid, exc=str(exc))
                    raise AllowlistDBError("db_error") from exc
                if org_id is not None:
                    return org_id

    # Path-based extraction: /v1/orgs/{org_id}/...
    path = request.url.path
    segments = path.split("/")
    try:
        orgs_idx = segments.index("orgs")
        return segments[orgs_idx + 1]
    except (ValueError, IndexError):
        pass
    return None


class AllowlistDBError(Exception):
    """Raised when the allowlist CIDRs cannot be loaded from the DB.

    Distinct from an org with zero configured entries: a DB error means we do
    NOT know whether an allowlist applies, so the middleware fails CLOSED
    (deny) rather than open. An empty result from a *successful* query stays
    allow-all (org has no allowlist configured).
    """


async def _load_cidrs(org_id: str) -> list[str]:
    """Load active CIDRs for the org from DB (with TTL cache).

    Returns the (possibly empty) CIDR list on success. Raises
    ``AllowlistDBError`` on any DB failure — the caller fails closed. A DB
    error is never cached, so the next request retries the DB.
    """
    now = time.monotonic()
    cached = _cache.get(org_id)
    if cached is not None and now < cached[1]:
        return cached[0]

    try:
        import uuid as _uuid

        from sqlalchemy import select

        from testlyn_api.core.db import _session_factory
        from testlyn_api.models.org_ip_allowlist import OrgIpAllowlist

        async with _session_factory() as session:
            result = await session.execute(
                select(OrgIpAllowlist.cidr).where(
                    OrgIpAllowlist.org_id == _uuid.UUID(org_id),
                    OrgIpAllowlist.active.is_(True),
                )
            )
            cidrs = [row[0] for row in result.all()]
    except Exception as exc:
        # Fail CLOSED (operator decision 2026-05-24): a DB blip must NOT
        # collapse to allow-all. Log at error as the alert signal — a
        # log-based Cloud Monitoring alert policy matches this event. Do not
        # cache the failure; re-raise so dispatch denies the request.
        log.error("ip_allowlist.db_error_fail_closed", org_id=org_id, exc=str(exc))
        raise AllowlistDBError(org_id) from exc

    _cache[org_id] = (cidrs, now + _CACHE_TTL)
    return cidrs


def invalidate_cache(org_id: str) -> None:
    """Call after mutating org_ip_allowlist so middleware picks up changes promptly."""
    _cache.pop(org_id, None)


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """Enforce per-org IP allowlist on /v1/ routes.

    When an org has no active entries the check is skipped (allow-all).
    Non-/v1/ paths are always allowed (healthz, docs, SCIM, SSO ACS).
    """

    def __init__(self, app: ASGIApp, trusted_proxy_depth: int = 1) -> None:
        super().__init__(app)
        self._trusted_depth = trusted_proxy_depth

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        org_id = None
        try:
            org_id = await _extract_org_id(request)
            if org_id is None:
                return await call_next(request)
            cidrs = await _load_cidrs(org_id)
        except AllowlistDBError:
            # Fail CLOSED on a DB error: we cannot confirm the request's IP is
            # allowed, so deny rather than silently bypass the control.
            log.error("ip_allowlist.denied_db_error", org_id=org_id, path=request.url.path)
            return Response(
                content='{"detail":"IP allowlist temporarily unavailable"}',
                status_code=403,
                headers={"Content-Type": "application/json"},
            )

        if not cidrs:
            # No allowlist configured — allow all
            return await call_next(request)

        client_ip = _extract_client_ip(request, self._trusted_depth)
        if _ip_in_cidr_list(client_ip, cidrs):
            return await call_next(request)

        log.warning(
            "ip_allowlist.blocked",
            org_id=org_id,
            client_ip=client_ip,
            path=request.url.path,
        )
        return Response(
            content='{"detail":"Your IP address is not allowed for this organization"}',
            status_code=403,
            headers={"Content-Type": "application/json"},
        )
