from __future__ import annotations

import hashlib

import structlog

from testlyn_api.core.cache import get_redis

log = structlog.get_logger(__name__)

_CACHE_TTL = 86_400 * 7  # 7 days — violations don't change often

_WCAG_FALLBACK_TPL = (
    "Refer to WCAG 2.2 Success Criterion for rule '{rule_id}' (impact: {impact}). "
    "See {help_url} for detailed guidance and code examples. "
    "Vertex AI credentials were not available to generate a tailored remediation."
)


def _snippet_hash(html_snippet: str) -> str:
    return hashlib.sha256(html_snippet.encode()).hexdigest()[:16]


def _redis_key(rule_id: str, snippet_hash: str) -> str:
    return f"a11y:remediation:{rule_id}:{snippet_hash}"


async def generate_remediation(
    *,
    rule_id: str,
    impact: str,
    html_snippet: str,
    help_url: str,
) -> str:
    """
    Return a 2-3 sentence remediation recommendation for an axe-core violation.

    Strategy:
    1. Check Redis cache keyed by (rule_id, html_snippet_hash).
    2. On cache miss, call Gemini Flash-Lite via Vertex AI.
    3. On any credential / network error, return a stock WCAG pointer string.

    The Postgres-level cache in a11y_violations_cache is written by the
    migration (0005) and populated by the worker after each audit run.
    This function uses Redis for hot-path lookups; Postgres cache is for
    cross-instance persistence queried separately.
    """
    snippet_hash = _snippet_hash(html_snippet)
    redis_key = _redis_key(rule_id, snippet_hash)

    redis = get_redis()
    try:
        cached = await redis.get(redis_key)
        if cached:
            log.debug("a11y.remediation.cache_hit", rule_id=rule_id)
            return cached
    except Exception:
        log.warning("a11y.remediation.redis_read_error", rule_id=rule_id)

    text = await _call_gemini(
        rule_id=rule_id,
        impact=impact,
        html_snippet=html_snippet,
        help_url=help_url,
    )

    try:
        await redis.set(redis_key, text, ex=_CACHE_TTL)
    except Exception:
        log.warning("a11y.remediation.redis_write_error", rule_id=rule_id)

    return text


async def _call_gemini(
    *,
    rule_id: str,
    impact: str,
    html_snippet: str,
    help_url: str,
) -> str:
    from testlyn_api.config import get_settings

    settings = get_settings()
    model_id = settings.gemini_model
    project = settings.gcp_project_id
    location = settings.vertex_ai_location

    fallback = _WCAG_FALLBACK_TPL.format(
        rule_id=rule_id, impact=impact, help_url=help_url
    )

    prompt = (
        "You are a WCAG 2.2 accessibility expert writing for a developer audience. "
        "Give a 2-3 sentence remediation recommendation for the following axe-core violation. "
        "Be specific: name the element, the fix, and the WCAG success criterion. No filler.\n\n"
        f"Rule ID: {rule_id}\n"
        f"Impact: {impact}\n"
        f"HTML snippet: {html_snippet[:500]}\n"
        f"Reference: {help_url}"
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
            log.warning("a11y.remediation.creds_missing", rule_id=rule_id)
            return fallback

        aiplatform.init(project=project, location=location, credentials=credentials)

        from vertexai.generative_models import GenerativeModel

        model = GenerativeModel(model_id)
        response = await model.generate_content_async(prompt)
        return response.text

    except ImportError:
        log.warning(
            "a11y.remediation.creds_missing",
            rule_id=rule_id,
            detail="google-cloud-aiplatform not installed",
        )
        return fallback
    except Exception as exc:
        log.warning(
            "a11y.remediation.vertex_error",
            rule_id=rule_id,
            detail=str(exc),
        )
        return fallback
