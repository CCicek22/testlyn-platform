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


def _extract_org_id(request: Request) -> str | None:
    """Best-effort org_id extraction for allowlist keying (same logic as rate limiter)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        try:
            import base64
            import json

            parts = token.split(".")
            if len(parts) == 3:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                return payload.get("org_id") or payload.get("orgId")
        except Exception:
            pass
    # Path-based extraction: /v1/orgs/{org_id}/...
    path = request.url.path
    segments = path.split("/")
    try:
        orgs_idx = segments.index("orgs")
        return segments[orgs_idx + 1]
    except (ValueError, IndexError):
        pass
    return None


async def _load_cidrs(org_id: str) -> list[str]:
    """Load active CIDRs for the org from DB (with TTL cache)."""
    now = time.monotonic()
    cached = _cache.get(org_id)
    if cached is not None and now < cached[1]:
        return cached[0]

    try:
        from sqlalchemy import select, text

        from testlyn_api.core.db import _session_factory
        from testlyn_api.models.org_ip_allowlist import OrgIpAllowlist

        async with _session_factory() as session:
            result = await session.execute(
                select(OrgIpAllowlist.cidr).where(
                    OrgIpAllowlist.org_id == text(f"'{org_id}'::uuid"),
                    OrgIpAllowlist.active.is_(True),
                )
            )
            cidrs = [row[0] for row in result.all()]
    except Exception as exc:
        log.warning("ip_allowlist.db_error", exc=str(exc))
        cidrs = []

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

        org_id = _extract_org_id(request)
        if org_id is None:
            return await call_next(request)

        cidrs = await _load_cidrs(org_id)
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
