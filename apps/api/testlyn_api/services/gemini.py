from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from testlyn_api.config import get_settings
from testlyn_api.core.cache import get_redis

log = structlog.get_logger(__name__)

_CACHE_TTL = 86_400  # 24h

_CANNED_SUMMARY = (
    "Could not connect to Vertex AI — credentials not available in this environment. "
    "Run summary is unavailable. "
    "Check Workload Identity setup for the Cloud Run service account."
)

_CANNED_BOTTLENECK = (
    "Could not connect to Vertex AI — credentials not available in this environment. "
    "Bottleneck analysis is unavailable. "
    "Check Workload Identity setup for the Cloud Run service account."
)


def _cache_key(namespace: str, payload: str) -> str:
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return f"gemini:{namespace}:{digest}"


import asyncio

_initialized = False
_credentials = None
_init_lock = asyncio.Lock()


async def _get_vertex_credentials() -> Any:
    global _credentials
    if _credentials is not None:
        return _credentials

    import google.auth
    
    def fetch_creds():
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return credentials

    try:
        _credentials = await asyncio.to_thread(fetch_creds)
    except Exception as exc:
        log.warning("vertex_creds_fetch_failed", error=str(exc))
        raise
    return _credentials


async def _cached_generate(namespace: str, prompt: str, fallback: str) -> str:
    redis = get_redis()
    key = _cache_key(namespace, prompt)

    try:
        cached = await redis.get(key)
        if cached is not None:
            return cached
    except Exception:
        log.warning("gemini.cache_read_error", key=key)

    result = await call_vertex(prompt, fallback)

    try:
        await redis.set(key, result, ex=_CACHE_TTL)
    except Exception:
        log.warning("gemini.cache_write_error", key=key)

    return result


async def call_vertex(prompt: str, fallback: str) -> str:
    global _initialized
    settings = get_settings()
    model_id = settings.gemini_model
    project = settings.gcp_project_id
    location = settings.vertex_ai_location

    try:
        import google.auth
        import google.auth.exceptions
        from google.cloud import aiplatform

        if not _initialized:
            async with _init_lock:
                if not _initialized:
                    try:
                        creds = await _get_vertex_credentials()
                    except google.auth.exceptions.DefaultCredentialsError:
                        log.warning(
                            "vertex_creds_missing",
                            model=model_id,
                        )
                        return fallback

                    # Run blocking aiplatform.init in a background thread
                    await asyncio.to_thread(
                        aiplatform.init,
                        project=project,
                        location=location,
                        credentials=creds,
                    )
                    _initialized = True

        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel(model_id)
        response = await model.generate_content_async(prompt)
        return response.text

    except ImportError:
        log.warning(
            "vertex_creds_missing",
            model=model_id,
            detail="google-cloud-aiplatform not installed",
        )
        return fallback
    except Exception as exc:
        log.warning(
            "vertex_creds_missing",
            model=model_id,
            detail=str(exc),
        )
        return fallback


async def summarize_run(
    run_id: str,
    summary_dict: dict[str, Any],
    *,
    sample_size_hint: int = 0,
) -> str:
    """Return a dev-to-dev 3-paragraph summary of a completed load test run."""
    prompt = (
        "You are a load-testing expert writing for a developer audience. "
        "Summarize the following load test run in exactly 3 short paragraphs. "
        "Use real numbers from the data. No marketing language.\n\n"
        f"Run ID: {run_id}\n"
        f"Summary data: {json.dumps(summary_dict, indent=2)}\n"
        f"Sample count hint: {sample_size_hint}"
    )
    return await _cached_generate("summarize_run", prompt, _CANNED_SUMMARY)


async def explain_bottleneck(metrics_json: dict[str, Any]) -> str:
    """Return a dev-to-dev 3-paragraph bottleneck analysis from raw metrics."""
    prompt = (
        "You are a load-testing expert writing for a developer audience. "
        "Identify the primary bottleneck in the following metrics in exactly 3 short paragraphs. "
        "Be specific: name the metric, the value, and what it implies. No filler.\n\n"
        f"Metrics: {json.dumps(metrics_json, indent=2)}"
    )
    return await _cached_generate("explain_bottleneck", prompt, _CANNED_BOTTLENECK)
