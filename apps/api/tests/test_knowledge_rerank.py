"""HTTP reranker client and settings wiring. httpx.MockTransport only, no network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from testlyn_api.config import Settings
from testlyn_api.knowledge import rerank
from testlyn_api.knowledge.rerank import HttpReranker, RerankError

URL = "http://reranker.test/v1/rerank"
DOCS = ["alpha", "beta", "gamma"]


def _reranker(
    handler: Any, *, api_key: str = "", timeout_s: float = 5.0
) -> HttpReranker:
    return HttpReranker(
        url=URL,
        model="test-reranker",
        api_key=api_key,
        timeout_s=timeout_s,
        transport=httpx.MockTransport(handler),
    )


async def test_posts_expected_body_and_returns_sorted_pairs() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.9},
                ]
            },
        )

    pairs = await _reranker(handler).rerank("q?", DOCS, top_n=2)

    assert seen["path"] == "/v1/rerank"
    assert seen["body"] == {
        "model": "test-reranker",
        "query": "q?",
        "documents": DOCS,
        "top_n": 2,
    }
    assert pairs == [(0, 0.9), (2, 0.2)]


async def test_sends_bearer_key_only_when_configured() -> None:
    auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        auth.append(request.headers.get("authorization"))
        return httpx.Response(
            200, json={"results": [{"index": 0, "relevance_score": 1.0}]}
        )

    await _reranker(handler, api_key="k-1").rerank("q", ["only"], top_n=1)
    await _reranker(handler).rerank("q", ["only"], top_n=1)

    assert auth == ["Bearer k-1", None]


@pytest.mark.parametrize(
    "content",
    [
        b'{"results": "nope"}',
        b'{"not_results": []}',
        b'{"results": [{"index": 0}]}',
        b'{"results": [{"index": 0, "relevance_score": "high"}]}',
        b'{"results": [{"index": 0, "relevance_score": NaN}]}',
        b'{"results": [{"index": 0, "relevance_score": Infinity}, {"index": 1, "relevance_score": 0.1}, {"index": 2, "relevance_score": 0.2}]}',
        b'{"results": [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.4}, {"index": 1, "relevance_score": 0.3}]}',
        b'{"results": [{"index": 0, "relevance_score": 0.5}, {"index": 3, "relevance_score": 0.4}, {"index": 1, "relevance_score": 0.3}]}',
        b'{"results": [{"index": -1, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.4}, {"index": 2, "relevance_score": 0.3}]}',
        b'{"results": [{"index": true, "relevance_score": 0.5}, {"index": 1, "relevance_score": 0.4}, {"index": 2, "relevance_score": 0.3}]}',
        b'{"results": [{"index": 0, "relevance_score": 0.5}]}',
        b"not json at all",
    ],
)
async def test_malformed_responses_raise_rerank_error(content: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    with pytest.raises(RerankError):
        await _reranker(handler).rerank("q", DOCS, top_n=3)


async def test_http_error_is_generic_and_leaks_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal secret-body-token")

    with pytest.raises(RerankError) as info:
        await _reranker(handler).rerank("q", DOCS, top_n=3)

    assert "secret-body-token" not in str(info.value)
    assert URL not in str(info.value)


async def test_transport_error_raises_rerank_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(RerankError):
        await _reranker(handler).rerank("q", DOCS, top_n=3)


def test_get_reranker_is_off_by_default() -> None:
    assert rerank.build_reranker(Settings(knowledge_reranker_url="")) is None


def test_get_reranker_builds_client_from_settings() -> None:
    settings = Settings(
        knowledge_reranker_url=URL,
        knowledge_reranker_model="m",
        knowledge_reranker_api_key="k",
        knowledge_reranker_deadline_seconds=3.0,
    )

    built = rerank.build_reranker(settings)

    assert isinstance(built, HttpReranker)
