"""POST /v1/orgs/{org_id}/knowledge/search on SQLite.

The two SQL legs are replaced with fake candidate lists, so these tests cover
validation, permissions, fusion and rerank wiring, transaction hygiene and
error mapping. Real SQL is covered in tests/postgres/test_knowledge_search.py.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
import httpx
from httpx import AsyncClient
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.config import Settings
from testlyn_api.knowledge import routes as knowledge_routes
from testlyn_api.knowledge import search
from testlyn_api.knowledge.embeddings import (
    EmbeddingError,
    HashingEmbedder,
    get_embedder,
)
from testlyn_api.knowledge.rerank import HttpReranker, RerankError, get_reranker
from testlyn_api.main import app
from testlyn_api.models.org import OrgMember

SEARCH_URL = "/v1/orgs/{org_id}/knowledge/search"


class _Recorder:
    """Stands in for both legs; records calls and returns canned hits."""

    def __init__(self, vector: list[search.Hit], keyword: list[search.Hit]) -> None:
        self.vector = vector
        self.keyword = keyword
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def vector_candidates(
        self, session: AsyncSession, **kwargs: Any
    ) -> list[search.Hit]:
        self.calls.append(("vector", kwargs))
        return list(self.vector)

    async def keyword_candidates(
        self, session: AsyncSession, **kwargs: Any
    ) -> list[search.Hit]:
        self.calls.append(("keyword", kwargs))
        return list(self.keyword)


def _hit(title: str, *, chunk_id: uuid.UUID | None = None) -> search.Hit:
    return search.Hit(
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        source="upload",
        heading="Heading",
        text=f"text of {title}",
        char_start=0,
        char_end=9,
    )


def _install_legs(monkeypatch: pytest.MonkeyPatch, recorder: _Recorder) -> None:
    monkeypatch.setattr(search, "vector_candidates", recorder.vector_candidates)
    monkeypatch.setattr(search, "keyword_candidates", recorder.keyword_candidates)


class _FakeEmbedder(HashingEmbedder):
    """Embeds with the hashing embedder and records calls and transaction state."""

    def __init__(self, db_session: AsyncSession | None = None) -> None:
        super().__init__()
        self.db_session = db_session
        self.in_transaction: bool | None = None
        self.embed_calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += 1
        if self.db_session is not None:
            self.in_transaction = self.db_session.in_transaction()
        return await super().embed(texts)


class _FakeReranker:
    def __init__(
        self,
        *,
        order: list[int] | None = None,
        error: Exception | None = None,
        delay_s: float = 0.0,
        db_session: AsyncSession | None = None,
    ) -> None:
        self.order = order
        self.error = error
        self.delay_s = delay_s
        self.db_session = db_session
        self.in_transaction: bool | None = None
        self.calls = 0

    async def rerank(
        self, query: str, documents: list[str], *, top_n: int
    ) -> list[tuple[int, float]]:
        self.calls += 1
        if self.db_session is not None:
            self.in_transaction = self.db_session.in_transaction()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        order = self.order if self.order is not None else list(range(len(documents)))
        return [(index, 1.0 - rank / 10) for rank, index in enumerate(order)][:top_n]


async def _create_org(client: AsyncClient, name: str) -> str:
    resp = await client.post("/v1/orgs", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _post_search(client: AsyncClient, org_id: str, **body: Any) -> Any:
    payload: dict[str, Any] = {"query": "rollback steps"}
    payload.update(body)
    return await client.post(SEARCH_URL.format(org_id=org_id), json=payload)


@pytest.fixture(autouse=True)
def _clear_search_overrides() -> None:
    yield
    app.dependency_overrides.pop(get_embedder, None)
    app.dependency_overrides.pop(get_reranker, None)


# ── Validation ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"query": ""},
        {"query": "   \n\t "},
        {"query": "x" * 1001},
        {"query": "a\x00b"},
        {"query": "ok", "top_k": 0},
        {"query": "ok", "top_k": 21},
        {"query": "ok", "mode": "fuzzy"},
        {"query": "ok", "project_id": "not-a-uuid"},
        {},
    ],
)
async def test_invalid_body_is_422(client: AsyncClient, body: dict[str, Any]) -> None:
    org_id = await _create_org(client, "Validation Org")

    resp = await client.post(SEARCH_URL.format(org_id=org_id), json=body)

    assert resp.status_code == 422


async def test_lone_surrogate_in_query_is_422(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Surrogate Org")
    raw = b'{"query":"\\ud800"}'

    resp = await client.post(
        SEARCH_URL.format(org_id=org_id),
        content=raw,
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 422


async def test_query_is_stripped_and_length_checked_after_strip(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Strip Org")
    recorder = _Recorder([], [])
    _install_legs(monkeypatch, recorder)
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    resp = await _post_search(client, org_id, query="  " + "x" * 998 + "  ")

    assert resp.status_code == 200
    keyword_kwargs = dict(recorder.calls)["keyword"]
    assert keyword_kwargs["query"] == "x" * 998


# ── Permissions ───────────────────────────────────────────────────────────────


async def test_non_member_is_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = await _create_org(client, "Stranger Search Org")
    await db_session.execute(
        delete(OrgMember).where(
            OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id
        )
    )
    await db_session.commit()
    recorder = _Recorder([], [])
    _install_legs(monkeypatch, recorder)

    resp = await _post_search(client, org_id)

    assert resp.status_code == 403
    assert recorder.calls == []


async def test_project_from_another_org_is_404(client: AsyncClient) -> None:
    org_a = await _create_org(client, "Search Tenant A")
    org_b = await _create_org(client, "Search Tenant B")
    project_b = (
        await client.post(f"/v1/orgs/{org_b}/projects", json={"name": "B"})
    ).json()["id"]

    resp = await _post_search(client, org_a, project_id=project_b)

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


async def test_viewer_can_search(
    client: AsyncClient,
    db_session: AsyncSession,
    dev_user_id: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = await _create_org(client, "Viewer Search Org")
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id)
        .values(role="viewer")
    )
    await db_session.commit()
    _install_legs(monkeypatch, _Recorder([], []))
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    assert (await _post_search(client, org_id)).status_code == 200


async def test_project_scope_is_passed_to_legs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Scope Org")
    project = (
        await client.post(f"/v1/orgs/{org_id}/projects", json={"name": "P"})
    ).json()["id"]
    recorder = _Recorder([], [])
    _install_legs(monkeypatch, recorder)
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    resp = await _post_search(client, org_id, project_id=project)

    assert resp.status_code == 200
    for _, kwargs in recorder.calls:
        assert kwargs["org_id"] == uuid.UUID(org_id)
        assert kwargs["project_id"] == uuid.UUID(project)


# ── Fusion wiring and modes ───────────────────────────────────────────────────


async def test_hybrid_fuses_both_legs_and_reports_ranks(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Fusion Org")
    both = _hit("Both")
    only_vector = _hit("Vector only")
    only_keyword = _hit("Keyword only")
    _install_legs(
        monkeypatch,
        _Recorder(vector=[both, only_vector], keyword=[only_keyword, both]),
    )
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    resp = await _post_search(client, org_id, top_k=5)

    body = resp.json()
    assert resp.status_code == 200
    assert body["mode"] == "hybrid"
    assert body["reranked"] is False
    titles = [r["document_title"] for r in body["results"]]
    assert titles[0] == "Both"
    assert set(titles) == {"Both", "Vector only", "Keyword only"}
    by_title = {r["document_title"]: r for r in body["results"]}
    assert by_title["Both"]["vector_rank"] == 1
    assert by_title["Both"]["keyword_rank"] == 2
    assert by_title["Vector only"]["keyword_rank"] is None
    assert by_title["Keyword only"]["vector_rank"] is None
    assert by_title["Both"]["score"] > by_title["Vector only"]["score"]
    assert set(body["results"][0]) == {
        "chunk_id",
        "document_id",
        "document_title",
        "source",
        "heading",
        "text",
        "char_start",
        "char_end",
        "score",
        "vector_rank",
        "keyword_rank",
    }


async def test_candidate_count_follows_top_k(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Candidates Org")
    recorder = _Recorder([], [])
    _install_legs(monkeypatch, recorder)
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    await _post_search(client, org_id, top_k=5)
    await _post_search(client, org_id, top_k=20)

    limits = [kwargs["limit"] for _, kwargs in recorder.calls[::2]]
    assert limits == [20, 80]


async def test_vector_mode_skips_keyword_leg(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Vector Mode Org")
    recorder = _Recorder([_hit("V")], [_hit("K")])
    _install_legs(monkeypatch, recorder)
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    body = (await _post_search(client, org_id, mode="vector")).json()

    assert [name for name, _ in recorder.calls] == ["vector"]
    assert [r["document_title"] for r in body["results"]] == ["V"]
    assert body["mode"] == "vector"


async def test_keyword_mode_never_calls_the_embedder(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Keyword Mode Org")
    recorder = _Recorder([_hit("V")], [_hit("K")])
    _install_legs(monkeypatch, recorder)
    embedder = _FakeEmbedder()
    app.dependency_overrides[get_embedder] = lambda: embedder

    body = (await _post_search(client, org_id, mode="keyword")).json()

    assert embedder.embed_calls == 0
    assert [name for name, _ in recorder.calls] == ["keyword"]
    assert [r["document_title"] for r in body["results"]] == ["K"]


# ── Transactions, reranking, and error mapping ───────────────────────────────


async def test_no_transaction_is_open_during_embedding_or_reranking(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id = await _create_org(client, "Probe Org")
    _install_legs(monkeypatch, _Recorder([_hit("A"), _hit("B")], []))
    embedder = _FakeEmbedder(db_session)
    reranker = _FakeReranker(db_session=db_session)
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_reranker] = lambda: reranker

    resp = await _post_search(client, org_id)

    assert resp.status_code == 200
    assert embedder.in_transaction is False
    assert reranker.calls == 1
    assert reranker.in_transaction is False


async def test_reranker_order_is_used_and_flagged(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Rerank Org")
    first, second, third = _hit("first"), _hit("second"), _hit("third")
    _install_legs(monkeypatch, _Recorder([first, second, third], []))
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    app.dependency_overrides[get_reranker] = lambda: _FakeReranker(order=[2, 0, 1])

    body = (await _post_search(client, org_id, top_k=3)).json()

    assert body["reranked"] is True
    assert [r["document_title"] for r in body["results"]] == [
        "third",
        "first",
        "second",
    ]


async def test_reranker_failure_falls_back_to_fused_order(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Rerank Fail Org")
    _install_legs(monkeypatch, _Recorder([_hit("one"), _hit("two")], []))
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    app.dependency_overrides[get_reranker] = lambda: _FakeReranker(
        error=RerankError("bad body from upstream")
    )

    resp = await _post_search(client, org_id, top_k=2)

    assert resp.status_code == 200
    assert resp.json()["reranked"] is False
    assert [r["document_title"] for r in resp.json()["results"]] == ["one", "two"]


async def test_reranker_timeout_falls_back_to_fused_order(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Rerank Timeout Org")
    _install_legs(monkeypatch, _Recorder([_hit("one"), _hit("two")], []))
    monkeypatch.setattr(
        knowledge_routes,
        "get_settings",
        lambda: Settings(knowledge_reranker_deadline_seconds=0.01),
    )
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    app.dependency_overrides[get_reranker] = lambda: _FakeReranker(delay_s=1.0)

    resp = await _post_search(client, org_id, top_k=2)

    assert resp.status_code == 200
    assert resp.json()["reranked"] is False
    assert [r["document_title"] for r in resp.json()["results"]] == ["one", "two"]


async def test_reranker_off_reports_false(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "No Rerank Org")
    _install_legs(monkeypatch, _Recorder([_hit("one")], []))
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()
    app.dependency_overrides[get_reranker] = lambda: None

    assert (await _post_search(client, org_id)).json()["reranked"] is False


class _Broken(HashingEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("upstream https://internal.example key=SECRET123")


class _Slow(HashingEmbedder):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(1.0)
        return await super().embed(texts)


async def test_embedder_failure_is_generic_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Broken Search Org")
    _install_legs(monkeypatch, _Recorder([], []))
    app.dependency_overrides[get_embedder] = lambda: _Broken()

    resp = await _post_search(client, org_id)

    assert resp.status_code == 503
    assert "internal.example" not in resp.text
    assert "SECRET123" not in resp.text


async def test_embedder_deadline_is_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Slow Search Org")
    _install_legs(monkeypatch, _Recorder([], []))
    monkeypatch.setattr(
        knowledge_routes,
        "get_settings",
        lambda: Settings(knowledge_embedding_deadline_seconds=0.01),
    )
    app.dependency_overrides[get_embedder] = lambda: _Slow()

    assert (await _post_search(client, org_id)).status_code == 503


def _http_reranker(handler: Any, url: str = "http://reranker.test/v1/rerank") -> Any:
    return HttpReranker(
        url=url,
        model="m",
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    "case",
    [
        "huge-score",
        "deep-json",
        "oversized-body",
        "invalid-url",
        "unexpected-exception",
    ],
)
async def test_reranker_bad_reply_falls_back_to_fused_order(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    org_id = await _create_org(client, f"Rerank Bad {case}")
    _install_legs(monkeypatch, _Recorder([_hit("one"), _hit("two")], []))
    app.dependency_overrides[get_embedder] = lambda: HashingEmbedder()

    if case == "huge-score":
        payload = b'{"results": [{"index": 0, "relevance_score": ' + b"9" * 400 + b"}]}"
        reranker: Any = _http_reranker(lambda r: httpx.Response(200, content=payload))
    elif case == "deep-json":
        payload = b'{"results": ' + b"[" * 100_000 + b"]" * 100_000 + b"}"
        reranker = _http_reranker(lambda r: httpx.Response(200, content=payload))
    elif case == "oversized-body":
        payload = b'{"results": []}' + b" " * (1_048_576 + 1)
        reranker = _http_reranker(lambda r: httpx.Response(200, content=payload))
    elif case == "invalid-url":
        reranker = HttpReranker(url="http://[::1", model="m")
    else:

        class _Exploding:
            async def rerank(
                self, query: str, documents: list[str], *, top_n: int
            ) -> list[tuple[int, float]]:
                raise RuntimeError("unexpected")

        reranker = _Exploding()
    app.dependency_overrides[get_reranker] = lambda: reranker

    resp = await _post_search(client, org_id, top_k=2)

    assert resp.status_code == 200
    assert resp.json()["reranked"] is False
    assert [r["document_title"] for r in resp.json()["results"]] == ["one", "two"]
