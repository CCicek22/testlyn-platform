"""Rate-limiting middleware (token bucket) for /v1/ routes.

Uses Memorystore (Redis) as the backing store.
Falls back to an in-process dict when Redis is unavailable — traffic still
served, a warning is logged per unavailability window.
"""
from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Any

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# Tier limits (requests per minute)                                             #
# --------------------------------------------------------------------------- #
TIER_RPM: dict[str, int] = {
    "free": 60,
    "hobby": 600,
    "pro": 6_000,
    "business": 60_000,
    # Any unrecognised plan treated as free
}

_WINDOW = 60  # seconds


# --------------------------------------------------------------------------- #
# Redis Lua script — atomic token-bucket check                                  #
# --------------------------------------------------------------------------- #
_LUA_SCRIPT = """
local key     = KEYS[1]
local limit   = tonumber(ARGV[1])
local window  = tonumber(ARGV[2])
local now     = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens     = tonumber(data[1]) or limit
local last_refill = tonumber(data[2]) or now

-- refill tokens proportional to elapsed time
local elapsed = now - last_refill
local refill  = math.floor(elapsed / window * limit)
tokens = math.min(limit, tokens + refill)

if tokens > 0 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, window * 2)
    return {1, tokens}
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, window * 2)
    return {0, tokens}
end
"""


# --------------------------------------------------------------------------- #
# In-process fallback store                                                     #
# --------------------------------------------------------------------------- #
class _InMemoryBucket:
    """Not thread-safe — acceptable for single-process dev/fallback."""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, float]] = defaultdict(
            lambda: {"tokens": 0.0, "last_refill": 0.0}
        )

    def check(self, key: str, limit: int) -> tuple[bool, int]:
        now = time.monotonic()
        b = self._buckets[key]
        if b["last_refill"] == 0.0:
            b["tokens"] = float(limit)
            b["last_refill"] = now

        elapsed = now - b["last_refill"]
        refill = (elapsed / _WINDOW) * limit
        tokens = min(float(limit), b["tokens"] + refill)
        b["last_refill"] = now

        if tokens >= 1.0:
            b["tokens"] = tokens - 1
            return True, int(b["tokens"])
        else:
            b["tokens"] = tokens
            return False, 0


_fallback = _InMemoryBucket()
_redis_unavailable_logged = False


class RateLimiter:
    """Token-bucket rate limiter.

    Usage::

        limiter = RateLimiter()
        allowed, remaining = await limiter.check(org_id="acme", plan="pro")
    """

    def __init__(self) -> None:
        self._redis: Any = None  # redis.asyncio.Redis | None
        self._script_sha: str | None = None

    async def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        try:
            import redis.asyncio as aioredis

            from testlyn_api.config import get_settings

            settings = get_settings()
            client = aioredis.from_url(settings.redis_url, decode_responses=False)
            # Quick connectivity probe
            await client.ping()
            self._redis = client
            return client
        except Exception:
            return None

    async def _load_script(self, redis_client: Any) -> str | None:
        if self._script_sha is not None:
            return self._script_sha
        try:
            sha = await redis_client.script_load(_LUA_SCRIPT)
            self._script_sha = sha
            return sha
        except Exception:
            return None

    async def check(self, org_id: str, plan: str) -> tuple[bool, int]:
        """Return (allowed, remaining_tokens).

        Falls back to in-memory when Redis is unreachable (with one warning log
        per unavailability episode).
        """
        global _redis_unavailable_logged
        limit = TIER_RPM.get(plan, TIER_RPM["free"])
        key = "rl:v1:" + hashlib.sha256(org_id.encode()).hexdigest()[:32]

        redis_client = await self._get_redis()
        if redis_client is None:
            if not _redis_unavailable_logged:
                logger.warning(
                    "rate_limiter.redis_unavailable",
                    msg="Falling back to in-process rate limiter — Memorystore unreachable",
                )
                _redis_unavailable_logged = True
            return _fallback.check(key, limit)

        _redis_unavailable_logged = False  # reset once Redis recovers

        sha = await self._load_script(redis_client)
        if sha is None:
            return _fallback.check(key, limit)

        try:
            now = int(time.time())
            result = await redis_client.evalsha(sha, 1, key, limit, _WINDOW, now)
            allowed = bool(result[0])
            remaining = int(result[1])
            return allowed, remaining
        except Exception as exc:
            logger.warning("rate_limiter.redis_error", exc=str(exc))
            return _fallback.check(key, limit)


# --------------------------------------------------------------------------- #
# Starlette middleware                                                          #
# --------------------------------------------------------------------------- #
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply token-bucket rate limiting to all /v1/ routes.

    Identity resolution order:
      1. ``X-Api-Key`` header → org_id from DB lookup (TODO: cache)
      2. ``Authorization: Bearer <jwt>`` → verified uid → (org_id, plan)
         resolved from the DB via ``core.org_context`` (cached). There is no
         ``org_id`` JWT claim; the plan must be live, so it comes from Postgres.
      3. Unauthenticated → apply ``free`` tier against the remote IP
    """

    def __init__(self, app: ASGIApp, limiter: RateLimiter | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Only apply to /v1/ paths
        if not request.url.path.startswith("/v1/"):
            return await call_next(request)

        org_id, plan = await self._resolve_identity(request)
        allowed, remaining = await self._limiter.check(org_id=org_id, plan=plan)

        if not allowed:
            limit = TIER_RPM.get(plan, TIER_RPM["free"])
            logger.info(
                "rate_limit.exceeded",
                org_id=org_id,
                plan=plan,
                path=request.url.path,
            )
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(_WINDOW),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        limit = TIER_RPM.get(plan, TIER_RPM["free"])
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    async def _resolve_identity(self, request: Request) -> tuple[str, str]:
        """Return (org_id_str, plan).

        Identity sources, in priority order:
        - X-Api-Key present → use hashed prefix as bucket key.
        - Bearer JWT → verify via Firebase (``token_verify.verify_token``) then
          resolve the org_id AND live plan from Postgres via
          ``org_context.resolve_org_and_plan`` (the verified token only carries
          ``uid`` — there is no ``org_id``/``plan`` claim). Unverified payloads
          are NEVER trusted — verification happens first, so an attacker cannot
          base64-encode a uid to steal another tenant's rate budget. The plan is
          read from the DB (cached) so paid tiers get their real RPM bucket
          instead of the free 60.
        - Fallback → remote IP, free tier.
        """
        from testlyn_api.core.org_context import OrgContextError, resolve_org_and_plan
        from testlyn_api.core.token_verify import extract_bearer, verify_token

        # --- X-Api-Key ---
        api_key = request.headers.get("X-Api-Key", "")
        if api_key:
            prefix = api_key[:16]
            return f"apikey:{prefix}", "free"  # plan lookup deferred

        # --- Bearer JWT (verified) ---
        token = extract_bearer(request.headers.get("Authorization", ""))
        if token is not None:
            claims = verify_token(token)
            if claims is not None:
                # Firebase verified tokens expose the user id as ``uid``; accept
                # the standard JWT ``sub``/``user_id`` aliases defensively.
                uid = claims.get("uid") or claims.get("user_id") or claims.get("sub")
                if uid:
                    # Cached DB lookup — one hit per user per TTL, not per request.
                    try:
                        org_id, plan = await resolve_org_and_plan(str(uid))
                        if org_id is not None:
                            return org_id, plan
                    except OrgContextError:
                        # Fail-open to "free" tier during database outages to preserve availability.
                        # Relies on downstream authentication middleware to enforce strict access rules.
                        pass

        # --- Fallback: IP-based ---
        client_ip = (request.client.host if request.client else "unknown")
        return f"ip:{client_ip}", "free"
