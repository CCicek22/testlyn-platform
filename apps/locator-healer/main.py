"""Locator healer — Cloud Run service.

POST /heal
  Body:  {screenshot_b64, dom_snapshot, failed_selector, page_url}
  Returns: {new_selector, confidence, reasoning}

Cache layer (Memorystore Redis → in-memory dict fallback).
Gemini 3.1 Pro vision call with LOCATOR_HEALING_ENABLED feature flag.
Creds-missing fallback: heuristic selector loosening.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

log = structlog.get_logger(__name__)

# Feature flag — set to "1" to enable Gemini Pro vision calls
LOCATOR_HEALING_ENABLED = os.getenv("LOCATOR_HEALING_ENABLED", "0") == "1"

REDIS_URL = os.getenv("REDIS_URL", "")
GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-3.1-pro")
GCP_PROJECT = os.getenv("GCP_PROJECT", "example-project-prod")
VERTEX_LOCATION = os.getenv("VERTEX_LOCATION", "us-central1")

_CACHE_TTL = 86_400  # 24h

# In-memory fallback when Redis is unavailable
_mem_cache: dict[str, dict[str, Any]] = {}

app = FastAPI(title="Testlyn Locator Healer", version="0.1.0")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class HealRequest(BaseModel):
    screenshot_b64: str
    dom_snapshot: str
    failed_selector: str
    page_url: str


class HealResponse(BaseModel):
    new_selector: str
    confidence: float  # 0.0–1.0
    reasoning: str


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_key(req: HealRequest) -> str:
    payload = json.dumps(
        {
            "failed_selector": req.failed_selector,
            "page_url": req.page_url,
            # DOM snapshot captures structural changes; screenshot is volatile
            "dom_hash": hashlib.sha256(req.dom_snapshot.encode()).hexdigest(),
        },
        sort_keys=True,
    )
    return f"healer:{hashlib.sha256(payload.encode()).hexdigest()}"


async def _cache_get(key: str) -> dict[str, Any] | None:
    if REDIS_URL:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(REDIS_URL, decode_responses=True)
            raw = await client.get(key)
            await client.aclose()
            if raw:
                return json.loads(raw)
        except Exception as exc:
            log.warning("healer.cache_redis_error", error=str(exc))

    return _mem_cache.get(key)


async def _cache_set(key: str, value: dict[str, Any]) -> None:
    if REDIS_URL:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(REDIS_URL, decode_responses=True)
            await client.set(key, json.dumps(value), ex=_CACHE_TTL)
            await client.aclose()
            return
        except Exception as exc:
            log.warning("healer.cache_redis_write_error", error=str(exc))

    _mem_cache[key] = value


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------


def _heuristic_heal(failed_selector: str) -> HealResponse:
    """Loosen a CSS selector by removing the last path segment."""
    # Strip the last CSS segment (e.g. "div.foo > span.bar" → "div.foo")
    stripped = re.sub(r"\s*[>+~]\s*[^\s>+~]+$", "", failed_selector.strip())
    if not stripped or stripped == failed_selector:
        # Fallback: strip last class or id qualifier
        stripped = re.sub(r"(\.|#)[^.#\s\[\]>+~]+$", "", failed_selector.strip()) or "*"

    return HealResponse(
        new_selector=stripped.strip() or "*",
        confidence=0.3,
        reasoning=(
            f"Heuristic fallback: removed last segment of '{failed_selector}'. "
            "Gemini vision is disabled (LOCATOR_HEALING_ENABLED=0) or creds unavailable."
        ),
    )


# ---------------------------------------------------------------------------
# Gemini Pro vision call
# ---------------------------------------------------------------------------


async def _gemini_heal(req: HealRequest) -> HealResponse:
    """Call Gemini 3.1 Pro vision to find a replacement selector."""
    prompt = (
        "You are a browser automation expert. A Playwright test failed because the CSS selector "
        f"'{req.failed_selector}' no longer matches an element on the page.\n\n"
        f"Page URL: {req.page_url}\n\n"
        "The attached screenshot shows the current page. "
        "The DOM snapshot is:\n"
        f"{req.dom_snapshot[:4000]}\n\n"
        "Return ONLY a JSON object with keys: new_selector (string), confidence (float 0-1), "
        "reasoning (string). No markdown."
    )

    try:
        import google.auth
        import google.auth.exceptions
        from google.cloud import aiplatform

        try:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        except google.auth.exceptions.DefaultCredentialsError:
            log.warning("healer.gemini_creds_missing", model=GEMINI_PRO_MODEL)
            return _heuristic_heal(req.failed_selector)

        aiplatform.init(project=GCP_PROJECT, location=VERTEX_LOCATION, credentials=credentials)

        from vertexai.generative_models import GenerativeModel, Image, Part

        model = GenerativeModel(GEMINI_PRO_MODEL)
        image_part = Part.from_image(Image.from_bytes(bytes.fromhex(req.screenshot_b64)))
        response = await model.generate_content_async([prompt, image_part])
        raw = response.text.strip()

        # Strip potential markdown fences
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        parsed = json.loads(raw)
        return HealResponse(
            new_selector=parsed["new_selector"],
            confidence=float(parsed.get("confidence", 0.8)),
            reasoning=parsed.get("reasoning", "Gemini Pro vision suggestion."),
        )

    except ImportError:
        log.warning("healer.gemini_not_installed", model=GEMINI_PRO_MODEL)
        return _heuristic_heal(req.failed_selector)
    except Exception as exc:
        log.warning("healer.gemini_error", error=str(exc))
        return _heuristic_heal(req.failed_selector)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@app.post("/heal", response_model=HealResponse)
async def heal(body: HealRequest) -> HealResponse:
    key = _cache_key(body)

    cached = await _cache_get(key)
    if cached:
        log.info("healer.cache_hit", selector=body.failed_selector)
        return HealResponse(**cached)

    log.info(
        "healer.cache_miss",
        selector=body.failed_selector,
        healing_enabled=LOCATOR_HEALING_ENABLED,
    )

    if LOCATOR_HEALING_ENABLED:
        result = await _gemini_heal(body)
    else:
        result = _heuristic_heal(body.failed_selector)

    await _cache_set(key, result.model_dump())
    return result


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8090")), log_level="info")
