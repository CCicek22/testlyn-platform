"""Optional reranker for knowledge search.

``HttpReranker`` calls a ``/v1/rerank``-style endpoint (request
``{model, query, documents, top_n}``, response ``{results: [{index,
relevance_score}]}``), the shape served by local rerank servers. Reranking is
off unless ``KNOWLEDGE_RERANKER_URL`` is set.
"""

from __future__ import annotations

import math
from typing import Protocol

import httpx

from testlyn_api.config import Settings, get_settings


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
                response = await client.post(self._url, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise RerankError(f"rerank request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise RerankError(f"rerank endpoint returned HTTP {response.status_code}")

        try:
            data = response.json()["results"]
            if not isinstance(data, list):
                raise TypeError("results is not a list")
            pairs = [(item["index"], float(item["relevance_score"])) for item in data]
        except (KeyError, TypeError, ValueError) as exc:
            raise RerankError("rerank response is malformed") from exc

        if len(pairs) != min(top_n, len(documents)):
            raise RerankError("rerank response has the wrong number of results")
        indices = [index for index, _ in pairs]
        for index in indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise RerankError("rerank index is not an integer")
            if not 0 <= index < len(documents):
                raise RerankError("rerank index is out of range")
        if len(set(indices)) != len(indices):
            raise RerankError("rerank indices are not unique")
        if not all(math.isfinite(score) for _, score in pairs):
            raise RerankError("rerank response contains non-finite scores")
        return sorted(pairs, key=lambda pair: (-pair[1], pair[0]))


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
