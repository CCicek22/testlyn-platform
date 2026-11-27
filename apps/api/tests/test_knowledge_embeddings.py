"""Embedders: hashing stand-in and OpenAI-compatible client (mock transport only)."""

from __future__ import annotations

import json
import math

import httpx
import pytest
from testlyn_api.knowledge.embeddings import (
    EmbeddingError,
    HashingEmbedder,
    OpenAICompatEmbedder,
)
from testlyn_api.models.knowledge import KNOWLEDGE_EMBEDDING_DIM


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_hashing_dim_and_normalisation() -> None:
    embedder = HashingEmbedder()
    (vec,) = await embedder.embed(["roll back the release"])
    assert embedder.dim == KNOWLEDGE_EMBEDDING_DIM == len(vec)
    assert math.isclose(math.sqrt(sum(x * x for x in vec)), 1.0, rel_tol=1e-9)


async def test_hashing_is_deterministic() -> None:
    embedder = HashingEmbedder()
    first = await embedder.embed(["Deploy the API service"])
    second = await HashingEmbedder().embed(["Deploy the API service"])
    assert first == second


async def test_hashing_is_case_insensitive() -> None:
    embedder = HashingEmbedder()
    (a,) = await embedder.embed(["Rollback Procedure"])
    (b,) = await embedder.embed(["rollback procedure"])
    assert a == b


async def test_hashing_similar_texts_are_closer_than_unrelated() -> None:
    embedder = HashingEmbedder()
    query, similar, unrelated = await embedder.embed(
        [
            "how do I roll back a failed release",
            "steps to roll back a failed release quickly",
            "invoice payment terms for enterprise customers",
        ]
    )
    assert _cosine(query, similar) > _cosine(query, unrelated)


async def test_hashing_batch_preserves_order() -> None:
    embedder = HashingEmbedder()
    texts = ["alpha beta", "gamma delta", "epsilon"]
    batch = await embedder.embed(texts)
    singles = [(await embedder.embed([t]))[0] for t in texts]
    assert batch == singles


def _mock_embeddings(
    *,
    dim: int = KNOWLEDGE_EMBEDDING_DIM,
    status: int = 200,
    seen: list[dict] | None = None,
    reverse: bool = False,
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": "secret-body-should-not-leak"})
        body = json.loads(request.content)
        if seen is not None:
            seen.append(
                {
                    "url": str(request.url),
                    "body": body,
                    "auth": request.headers.get("authorization"),
                }
            )
        items = [
            {"index": i, "embedding": [float(i)] * dim}
            for i in range(len(body["input"]))
        ]
        if reverse:
            items.reverse()
        return httpx.Response(200, json={"object": "list", "data": items})

    return httpx.MockTransport(handler)


async def test_openai_compat_batches_and_posts_to_embeddings_path() -> None:
    seen: list[dict] = []
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1/",
        model="embeddinggemma",
        api_key="k-test",
        batch_size=2,
        transport=_mock_embeddings(seen=seen),
    )
    vectors = await embedder.embed(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert [len(call["body"]["input"]) for call in seen] == [2, 2, 1]
    assert seen[0]["url"] == "http://embed.test/v1/embeddings"
    assert seen[0]["body"]["model"] == "embeddinggemma"
    assert seen[0]["auth"] == "Bearer k-test"


async def test_openai_compat_orders_by_index() -> None:
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        batch_size=3,
        transport=_mock_embeddings(reverse=True),
    )
    vectors = await embedder.embed(["x", "y", "z"])
    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]


async def test_openai_compat_empty_input_makes_no_request() -> None:
    seen: list[dict] = []
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        transport=_mock_embeddings(seen=seen),
    )
    assert await embedder.embed([]) == []
    assert seen == []


async def test_openai_compat_wrong_dimension_raises() -> None:
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1", model="m", transport=_mock_embeddings(dim=255)
    )
    with pytest.raises(EmbeddingError, match="dimension 255, expected 256"):
        await embedder.embed(["one"])


async def test_openai_compat_http_error_is_wrapped_without_body() -> None:
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        transport=_mock_embeddings(status=503),
    )
    with pytest.raises(EmbeddingError, match="HTTP 503") as info:
        await embedder.embed(["one"])
    assert "secret-body" not in str(info.value)


async def test_openai_compat_transport_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError, match="ConnectError"):
        await embedder.embed(["one"])


async def test_openai_compat_count_mismatch_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.0] * KNOWLEDGE_EMBEDDING_DIM}]},
        )

    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError, match="1 vectors for 2 inputs"):
        await embedder.embed(["one", "two"])


async def test_openai_compat_malformed_response_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1",
        model="m",
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError, match="malformed"):
        await embedder.embed(["one"])


def test_openai_compat_rejects_zero_batch_size() -> None:
    with pytest.raises(ValueError):
        OpenAICompatEmbedder(base_url="http://embed.test/v1", model="m", batch_size=0)


def test_get_embedder_selects_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from testlyn_api.config import Settings
    from testlyn_api.knowledge import embeddings

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: Settings(knowledge_embedding_provider="hashing"),
    )
    assert isinstance(embeddings.get_embedder(), HashingEmbedder)

    monkeypatch.setattr(
        embeddings,
        "get_settings",
        lambda: Settings(
            knowledge_embedding_provider="openai_compat",
            knowledge_embedding_base_url="http://embed.test/v1",
        ),
    )
    assert isinstance(embeddings.get_embedder(), OpenAICompatEmbedder)


async def test_hashing_golden_bucket_and_sign() -> None:
    # Fixed by blake2b(digest_size=8): bucket 95, sign -1. Fails if the hash
    # ever becomes salted (e.g. built-in hash()) or changes algorithm.
    (vec,) = await HashingEmbedder().embed(["rollback"])
    nonzero = [(i, x) for i, x in enumerate(vec) if x != 0.0]
    assert nonzero == [(95, -1.0)]


async def test_hashing_cyrillic_and_cjk_are_not_zero_and_findable() -> None:
    embedder = HashingEmbedder()
    cyr_query, cyr_similar, cyr_other, cjk = await embedder.embed(
        [
            "откат релиза",
            "как выполнить откат релиза",
            "счёт за услуги",
            "发布回滚步骤",
        ]
    )
    for vec in (cyr_query, cyr_similar, cyr_other, cjk):
        assert any(x != 0.0 for x in vec)
    assert _cosine(cyr_query, cyr_similar) > _cosine(cyr_query, cyr_other)


async def test_hashing_punctuation_only_text_is_non_zero_and_deterministic() -> None:
    embedder = HashingEmbedder()
    (first,) = await embedder.embed(["--- !!! ---"])
    (second,) = await HashingEmbedder().embed(["--- !!! ---"])
    assert any(x != 0.0 for x in first)
    assert first == second
    assert math.isclose(math.sqrt(sum(x * x for x in first)), 1.0, rel_tol=1e-9)


def _raw_response(payload: bytes) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=payload, headers={"content-type": "application/json"}
        )

    return httpx.MockTransport(handler)


async def test_openai_compat_rejects_duplicate_indices() -> None:
    dim = KNOWLEDGE_EMBEDDING_DIM
    vec = [0.0] * dim
    payload = json.dumps(
        {"data": [{"index": 0, "embedding": vec}, {"index": 0, "embedding": vec}]}
    ).encode()
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1", model="m", transport=_raw_response(payload)
    )
    with pytest.raises(EmbeddingError, match="indices"):
        await embedder.embed(["a", "b"])


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
async def test_openai_compat_rejects_non_finite_values(bad: str) -> None:
    dim = KNOWLEDGE_EMBEDDING_DIM
    values = ["0.0"] * dim
    values[3] = bad
    payload = ('{"data":[{"index":0,"embedding":[' + ",".join(values) + "]}]}").encode()
    embedder = OpenAICompatEmbedder(
        base_url="http://embed.test/v1", model="m", transport=_raw_response(payload)
    )
    with pytest.raises(EmbeddingError, match="non-finite"):
        await embedder.embed(["a"])
