from __future__ import annotations

import structlog
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> JSONResponse:
    """
    Stripe webhook stub — Phase 1.
    Returns 200 and logs the event type. Real Stripe integration in Phase 1 follow-up.
    """
    try:
        payload = await request.json()
        event_type = payload.get("type", "unknown")
        log.info("webhook.stripe", event_type=event_type)
    except Exception:
        log.warning("webhook.stripe_parse_error")

    return JSONResponse({"received": True})
