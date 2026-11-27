"""Optional reranker for knowledge search.

``HttpReranker`` calls a ``/v1/rerank``-style endpoint (request
``{model, query, documents, top_n}``, response ``{results: [{index,
relevance_score}]}``), the shape served by local rerank servers. Reranking is
off unless ``KNOWLEDGE_RERANKER_URL`` is set.
"""

from __future__ import annotations

import json
import math
from typing import Protocol

import httpx

from testlyn_api.config import Settings, get_settings


# Largest reranker reply accepted. Our requests carry at most 100 short documents.
MAX_RESPONSE_BYTES = 1_048_576


class RerankError(Exception):
    """Reranker call failed or returned unusable results."""


class Reranker(Protocol):
    async def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]: ...


class HttpReranker:
    """Client for a rerank endpoint. Returns ``(index, score)`` pairs, best first.

    ``transport`` exists so tests can inject ``httpx.MockTransport``.
    """

    def __init__(
        self,
        *,
        url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._transport = transport

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body = {
            "model": self._model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                async with client.stream(
                    "POST", self._url, json=body, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        raise RerankError(
                            f"rerank endpoint returned HTTP {response.status_code}"
                        )
                    payload = await _read_capped(response)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            raise RerankError(f"rerank request failed: {type(exc).__name__}") from exc

        expected = min(top_n, len(documents))
        try:
            data = json.loads(payload)["results"]
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise RerankError("rerank response is malformed") from exc
        if not isinstance(data, list):
            raise RerankError("rerank response is malformed")
        # Servers may return more than top_n; keep the best `expected` of them.
        if not expected <= len(data) <= len(documents):
            raise RerankError("rerank response has the wrong number of results")
        try:
            raw = [(item["index"], item["relevance_score"]) for item in data]
        except (KeyError, TypeError) as exc:
            raise RerankError("rerank response is malformed") from exc

        indices = [index for index, _ in raw]
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise RerankError("rerank index is not an integer")
            if not 0 <= index < len(documents):
                raise RerankError("rerank index is out of range")
        if len(set(indices)) != len(indices):
            raise RerankError("rerank indices are not unique")
        pairs = [(index, _score(value)) for index, value in raw]
        return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))[:expected]


async def _read_capped(response: httpx.Response) -> bytes:
    """Read the body, refusing anything over MAX_RESPONSE_BYTES."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise RerankError("rerank response is too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _score(value: object) -> float:
    """A real, finite number. bool and strings are not scores."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RerankError("rerank score is not a number")
    try:
        score = float(value)
    except OverflowError as exc:
        raise RerankError("rerank score is out of range") from exc
    if not math.isfinite(score):
        raise RerankError("rerank response contains non-finite scores")
    return score


def build_reranker(settings: Settings) -> Reranker | None:
    """The reranker selected by settings, or None when reranking is off."""
    if not settings.knowledge_reranker_url:
        return None
    return HttpReranker(
        url=settings.knowledge_reranker_url,
        model=settings.knowledge_reranker_model,
        api_key=settings.knowledge_reranker_api_key,
        timeout_s=settings.knowledge_reranker_deadline_seconds,
    )


def get_reranker() -> Reranker | None:
    return build_reranker(get_settings())
