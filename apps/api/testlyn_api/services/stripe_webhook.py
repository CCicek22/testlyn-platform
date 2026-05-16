from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.config import get_settings
from testlyn_api.models.org import Organization
from testlyn_api.models.stripe_event import StripeEventLog

log = structlog.get_logger(__name__)

_PLACEHOLDER = "sk_test_PLACEHOLDER"

# Maps Stripe subscription status to Testlyn plan slugs.
_STATUS_TO_PLAN: dict[str, str] = {
    "active": "hobby",  # refined further via price_id lookup if needed
    "trialing": "hobby",
    "past_due": "past_due",
    "canceled": "free",
    "unpaid": "past_due",
    "incomplete": "free",
    "incomplete_expired": "free",
    "paused": "free",
}


def _price_to_plan() -> dict[str, str]:
    """Build price-id -> plan slug map from Settings on every call.

    Cheap (one dict construction); avoids the import-time global that previously
    cached env at module load and prevented Settings overrides from taking
    effect during tests.
    """
    settings = get_settings()
    mapping: dict[str, str] = {}
    if settings.stripe_price_hobby:
        mapping[settings.stripe_price_hobby] = "hobby"
    if settings.stripe_price_pro:
        mapping[settings.stripe_price_pro] = "pro"
    if settings.stripe_price_business:
        mapping[settings.stripe_price_business] = "business"
    return mapping


def _plan_from_subscription(sub: dict[str, Any]) -> str:
    status = sub.get("status", "")
    price_to_plan = _price_to_plan()
    # Try to find plan from price id first
    items = sub.get("items", {}).get("data", [])
    for item in items:
        price_id = item.get("price", {}).get("id", "")
        if price_id in price_to_plan:
            return price_to_plan[price_id]
    return _STATUS_TO_PLAN.get(status, "free")


async def _is_processed(event_id: str, session: AsyncSession) -> bool:
    result = await session.execute(
        select(StripeEventLog).where(StripeEventLog.stripe_event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def _mark_processed(event_id: str, event_type: str, session: AsyncSession) -> None:
    row = StripeEventLog(stripe_event_id=event_id, event_type=event_type)
    session.add(row)
    await session.flush()


async def _upsert_org_from_subscription(
    sub: dict[str, Any],
    session: AsyncSession,
) -> None:
    customer_id: str = sub.get("customer", "")
    if not customer_id:
        log.warning("stripe_webhook.no_customer_id", sub_id=sub.get("id"))
        return

    result = await session.execute(
        select(Organization).where(Organization.stripe_customer_id == customer_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        log.warning("stripe_webhook.org_not_found", customer_id=customer_id)
        return

    org.plan = _plan_from_subscription(sub)
    org.stripe_customer_id = customer_id
    await session.flush()
    log.info("stripe_webhook.org_updated", org_id=str(org.id), plan=org.plan)


async def handle_event(
    raw_body: bytes,
    sig_header: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Verify and dispatch a Stripe webhook event.

    Returns a dict suitable for a 200 JSON response.
    On placeholder key config: logs warning, returns 200 without acting.
    """
    import stripe

    settings = get_settings()
    secret_key = settings.stripe_secret_key
    webhook_secret = settings.stripe_webhook_secret
    if webhook_secret == "whsec_PLACEHOLDER":
        webhook_secret = ""

    if secret_key == _PLACEHOLDER:
        log.warning(
            "stripe_placeholder_config",
            detail="STRIPE_SECRET_KEY is placeholder; skipping webhook processing",
        )
        return {"received": True, "processed": False, "reason": "placeholder_config"}

    if not webhook_secret:
        log.warning("stripe_webhook.no_webhook_secret")
        return {"received": True, "processed": False, "reason": "no_webhook_secret"}

    try:
        event = stripe.Webhook.construct_event(raw_body, sig_header, webhook_secret)
    except stripe.errors.SignatureVerificationError as exc:
        log.warning("stripe_webhook.invalid_signature", detail=str(exc))
        raise

    event_id: str = event["id"]
    event_type: str = event["type"]

    if await _is_processed(event_id, session):
        log.info("stripe_webhook.duplicate", event_id=event_id)
        return {"received": True, "processed": False, "reason": "duplicate"}

    data_object: dict[str, Any] = event["data"]["object"]

    if event_type in (
        "customer.subscription.created",
        "customer.subscription.updated",
    ):
        await _upsert_org_from_subscription(data_object, session)

    elif event_type == "customer.subscription.deleted":
        data_object = dict(data_object)
        data_object["status"] = "canceled"
        await _upsert_org_from_subscription(data_object, session)

    elif event_type == "invoice.payment_failed":
        customer_id: str = data_object.get("customer", "")
        if customer_id:
            result = await session.execute(
                select(Organization).where(Organization.stripe_customer_id == customer_id)
            )
            org = result.scalar_one_or_none()
            if org:
                org.plan = "past_due"
                await session.flush()
                log.info("stripe_webhook.payment_failed", org_id=str(org.id))

    else:
        log.info("stripe_webhook.unhandled_event", event_type=event_type)

    await _mark_processed(event_id, event_type, session)
    await session.commit()

    return {"received": True, "processed": True, "event_type": event_type}
