"""Shared Firebase ID-token verification helper for middleware.

The auth dependency (``core.auth.get_current_user``) verifies the Bearer token
on every authenticated request. Middlewares that need to read JWT claims
(rate limit, IP allowlist) cannot trust the raw payload — an attacker can
forge any field by base64-encoding their own JSON. They must call
``firebase_admin.auth.verify_id_token`` (signature + expiry check) too.

To keep per-request overhead reasonable, verified claims are cached in-process
keyed by ``sha256(token)`` for a short TTL. Cache lookup is cheap; verification
is skipped on cache hit.

Returns ``None`` on any failure (missing import, invalid sig, expired). Callers
treat ``None`` as "unauthenticated" and fall back to their unauthenticated
behaviour (e.g. IP-based rate limit keying).
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# Short TTL — tokens are 1-hour Firebase IDs; cache 60 s to bound staleness on
# token revocation while keeping verification overhead negligible.
_CACHE_TTL = 60.0
_cache: dict[str, tuple[dict[str, Any], float]] = {}


def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a Firebase ID token and return its claims, or ``None``.

    Cached for ``_CACHE_TTL`` seconds per distinct token. ``verify_id_token``
    performs blocking network I/O (JWKS fetch) so it runs in a worker thread —
    never directly on the event loop.
    """
    if not token:
        return None

    now = time.monotonic()
    key = _key(token)
    cached = _cache.get(key)
    if cached is not None and now < cached[1]:
        return cached[0]

    try:
        import firebase_admin.auth as fb_auth

        decoded = await asyncio.to_thread(fb_auth.verify_id_token, token)
    except Exception as exc:  # noqa: BLE001 — verify_id_token raises many subclasses
        log.debug("token_verify.failed", error=str(exc))
        return None

    _cache[key] = (decoded, now + _CACHE_TTL)
    return decoded


def extract_bearer(authorization_header: str) -> str | None:
    """Return the token after ``Bearer `` prefix, or ``None``."""
    if not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[7:].strip()
    return token or None
