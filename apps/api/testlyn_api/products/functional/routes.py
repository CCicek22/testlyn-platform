from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status

from testlyn_api.deps import CurrentUserDep
from testlyn_api.products.functional._gemini import generate_playwright_script
from testlyn_api.products.functional.schemas import (
    FunctionalGenerateRequest,
    FunctionalGenerateResponse,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/products/functional", tags=["functional"])


@router.post(
    "/generate",
    response_model=FunctionalGenerateResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_test(
    body: FunctionalGenerateRequest,
    current_user: CurrentUserDep,
) -> FunctionalGenerateResponse:
    """Generate a Playwright TypeScript test script from natural language or a PRD.

    When Vertex AI credentials are unavailable, returns a deterministic template
    based on target_url so the system remains usable without GCP credentials.
    """
    if not body.prompt and not body.prd_file and not body.target_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of prompt, prd_file, or target_url is required.",
        )

    script_ts, locator_strategies = await generate_playwright_script(
        prompt=body.prompt,
        prd_file=body.prd_file,
        target_url=body.target_url,
    )

    log.info(
        "functional.generate",
        user_id=str(current_user),
        target_url=body.target_url,
        has_prompt=body.prompt is not None,
    )

    return FunctionalGenerateResponse(
        script_ts=script_ts,
        locator_strategies=locator_strategies,
    )


@router.post(
    "/heal",
    status_code=status.HTTP_200_OK,
)
async def heal_selector(
    body: dict,
    current_user: CurrentUserDep,
) -> dict:
    """Proxy to the locator-healer microservice.

    Accepts: {screenshot_b64, dom_snapshot, failed_selector, page_url}
    Returns: {new_selector, confidence, reasoning}
    """
    import os

    import httpx

    healer_url = os.getenv("LOCATOR_HEALER_URL", "http://localhost:8090")

    required = {"screenshot_b64", "dom_snapshot", "failed_selector", "page_url"}
    missing = required - body.keys()
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing fields: {sorted(missing)}",
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{healer_url}/heal", json=body)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("functional.heal_proxy_error", status=exc.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Locator healer returned an error.",
        ) from exc
    except Exception as exc:
        log.error("functional.heal_proxy_unreachable", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Locator healer is unreachable.",
        ) from exc
