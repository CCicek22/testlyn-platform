from __future__ import annotations

import structlog
from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from testlyn_api.deps import SessionDep
from testlyn_api.services import stripe_webhook as svc

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    session: SessionDep,
    stripe_signature: str | None = Header(None, alias="stripe-signature"),
) -> JSONResponse:
    """Verify and dispatch Stripe webhook events."""
    raw_body = await request.body()
    sig = stripe_signature or ""

    try:
        import stripe as stripe_lib

        result = await svc.handle_event(raw_body, sig, session)
        return JSONResponse(result)
    except stripe_lib.SignatureVerificationError as sig_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        ) from sig_err
    except Exception as exc:
        log.exception("webhook.stripe_error", detail=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing error",
        ) from exc
