"""Firebase ID-token verification for chat endpoints.

Mirrors apps/api/testlyn_api/core/token_verify.py — short in-process cache
keyed by sha256(token) to amortize firebase_admin.auth.verify_id_token cost.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import structlog
from cachetools import LRUCache
from fastapi import HTTPException, Request, status

from testlyn_chat.config import get_settings

log = structlog.get_logger(__name__)

_CACHE_TTL = 60.0
_cache: LRUCache[str, tuple[dict[str, Any], float]] = LRUCache(maxsize=1000)
_firebase_initialised = False


def _ensure_firebase_init() -> None:
    """Idempotently initialise the Firebase Admin default app."""
    global _firebase_initialised
    if _firebase_initialised:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        if not firebase_admin._apps:  # type: ignore[attr-defined]
            settings = get_settings()
            firebase_admin.initialize_app(
                credentials.ApplicationDefault(),
                {"projectId": settings.firebase_project_id},
            )
        _firebase_initialised = True
    except Exception as exc:  # noqa: BLE001
        log.error("auth.firebase_init_failed", error=str(exc))
        raise


def _key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a Firebase ID token; cache claims for ``_CACHE_TTL`` seconds."""
    if not token:
        return None

    now = time.monotonic()
    key = _key(token)
    cached = _cache.get(key)
    if cached is not None and now < cached[1]:
        return cached[0]

    try:
        _ensure_firebase_init()
        import firebase_admin.auth as fb_auth

        decoded = fb_auth.verify_id_token(token)
    except Exception as exc:  # noqa: BLE001 — verify_id_token raises many subclasses
        log.debug("auth.verify_failed", error=str(exc))
        return None

    _cache[key] = (decoded, now + _CACHE_TTL)
    return decoded


def extract_bearer(authorization_header: str | None) -> str | None:
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return None
    token = authorization_header[7:].strip()
    return token or None


async def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI dependency: verify Bearer token, return claims, else 401.

    The full bearer token is stashed on ``request.state.user_token`` so
    downstream tools can forward it to testlyn-api on the user's behalf
    (we never mint our own service-account JWT for user-scoped calls).
    """
    token = extract_bearer(request.headers.get("authorization"))
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )

    claims = verify_token(token)
    if claims is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    request.state.user_token = token
    request.state.user_claims = claims
    return claims
