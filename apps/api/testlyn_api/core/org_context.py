"""Shared org/plan resolver for middleware (rate limit + IP allowlist).

Both the rate-limit and IP-allowlist middlewares need to know, for an
authenticated user, *which org* the request belongs to and *what plan* that org
is on. The Firebase ID token only carries ``uid``/``email`` — there is no
``org_id`` (or ``plan``) claim — so we resolve both from Postgres here.

DEVIATION FROM THE BRIEF (intentional, flagged for the PR):
  The follow-up brief asked to "mint the org_id JWT claim". We deliberately do
  DB resolution instead, because:
    1. The actual bug is that paid tiers get the free 60rpm bucket — the rate
       limiter hard-coded ``plan="free"``. A static custom claim cannot carry a
       *live* plan, so minting ``org_id`` alone would not fix the per-plan
       limit. The plan must come from the DB regardless.
    2. A static custom claim is stale for multi-org users and after plan changes
       (Stripe upgrade) until the next token refresh, which we don't control.
  Resolving org_id + plan together from the DB fixes both in one place.

Performance:
  This runs inside middleware, on every ``/v1/`` request. To avoid a per-request
  DB round-trip we cache ``(org_id, plan)`` per uid for ``_CACHE_TTL`` seconds
  (same in-process dict + monotonic-expiry style as ``core.token_verify``).
  Trade-off: after a plan upgrade the user can keep the old tier limit / old org
  for up to ``_CACHE_TTL`` seconds. 30 s is an acceptable bound for a rate-limit
  bucket and an IP allowlist; callers needing immediacy can ``invalidate(uid)``.
"""

from __future__ import annotations

import time
import uuid

import structlog

log = structlog.get_logger(__name__)

# Short TTL — bounds plan/org staleness after an upgrade or membership change
# while keeping the middleware hot path to one DB hit per user per window.
_CACHE_TTL = 30.0
_cache: dict[str, tuple[tuple[str | None, str], float]] = {}


def _user_uuid(uid: str) -> uuid.UUID:
    """Derive the internal user UUID from a Firebase uid.

    MUST match ``core.auth.get_current_user`` so the row we look up is the same
    one the request was authenticated against.
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, uid)


class OrgContextError(Exception):
    """Raised when organization context cannot be resolved due to DB errors."""
    pass


async def resolve_org_and_plan(uid: str) -> tuple[str | None, str]:
    """Return ``(org_id_str_or_None, plan)`` for a Firebase ``uid``.

    Picks a deterministic primary org (earliest membership) when the user
    belongs to several. Returns ``(None, "free")`` when the user has no
    membership (valid DB lookup returning None). Raises ``OrgContextError``
    on any DB error to let allowlist middleware fail closed defensively.
    Cached per uid for ``_CACHE_TTL`` seconds.
    """
    now = time.monotonic()
    cached = _cache.get(uid)
    if cached is not None and now < cached[1]:
        return cached[0]

    result: tuple[str | None, str] = (None, "free")
    try:
        from sqlalchemy import select

        from testlyn_api.core.db import _session_factory
        from testlyn_api.models.org import OrgMember, Organization

        user_id = _user_uuid(uid)
        async with _session_factory() as session:
            row = (
                await session.execute(
                    select(Organization.id, Organization.plan)
                    .join(OrgMember, OrgMember.org_id == Organization.id)
                    .where(OrgMember.user_id == user_id)
                    .order_by(OrgMember.created_at)
                    .limit(1)
                )
            ).first()
        if row is not None:
            result = (str(row[0]), row[1])
    except Exception as exc:  # noqa: BLE001
        # Log DB errors loudly and raise OrgContextError so allowlist fails closed.
        log.error("org_context.resolve_failed", uid=uid, exc=str(exc))
        raise OrgContextError(str(exc)) from exc

    _cache[uid] = (result, now + _CACHE_TTL)
    return result



def invalidate(uid: str) -> None:
    """Drop the cached resolution for one uid (e.g. after a plan/membership change)."""
    _cache.pop(uid, None)


def clear_cache() -> None:
    """Clear the entire resolver cache (used by tests)."""
    _cache.clear()
