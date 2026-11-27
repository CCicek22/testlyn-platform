"""Knowledge store: ingestion service and /v1/orgs/{org_id}/knowledge routes (SQLite)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.config import Settings
from testlyn_api.knowledge import routes as knowledge_routes
from testlyn_api.knowledge import service
from testlyn_api.knowledge.embeddings import (
    EmbeddingError,
    HashingEmbedder,
    get_embedder,
)
from testlyn_api.main import app
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument
from testlyn_api.models.org import OrgMember
from testlyn_api.models.project import Project
from testlyn_api.models.project_role_override import ProjectRoleOverride
from testlyn_api.schemas.knowledge import KnowledgeDocumentCreate

RUNBOOK = """# Runbook

Intro about the service.

## Rollback

Run the revert job and wait for green.

```bash
kubectl rollout undo deploy/api
```
"""


class _FailingEmbedder:
    model_name = "failing"
    dim = 256

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("boom")


async def _create_org(client: AsyncClient, name: str) -> str:
    resp = await client.post("/v1/orgs", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _post_doc(
    client: AsyncClient, org_id: str, **overrides: object
) -> httpx.Response:
    body: dict[str, object] = {"title": "Runbook", "source": "upload", "text": RUNBOOK}
    body.update(overrides)
    return await client.post(f"/v1/orgs/{org_id}/knowledge/documents", json=body)


def _walk_keys(obj: object) -> set[str]:
    if isinstance(obj, dict):
        keys = set(obj)
        for value in obj.values():
            keys |= _walk_keys(value)
        return keys
    if isinstance(obj, list):
        keys: set[str] = set()
        for value in obj:
            keys |= _walk_keys(value)
        return keys
    return set()


# ── Service ───────────────────────────────────────────────────────────────────


async def test_service_rolls_back_when_embedder_fails(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    with pytest.raises(EmbeddingError):
        await service.ingest_document(
            db_session,
            org_id=dev_org_id,
            project_id=None,
            title="t",
            source="upload",
            text=RUNBOOK,
            created_by=None,
            embedder=_FailingEmbedder(),
            max_chars=10_000,
            max_chunks=10_000,
            embed_deadline_s=None,
        )
    docs = (await db_session.execute(select(KnowledgeDocument))).scalars().all()
    chunks = (await db_session.execute(select(KnowledgeChunk))).scalars().all()
    assert docs == []
    assert chunks == []


async def test_service_rejects_oversized_and_empty_text(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    common = {
        "org_id": dev_org_id,
        "project_id": None,
        "title": "t",
        "source": "upload",
        "created_by": None,
        "embedder": HashingEmbedder(),
    }
    with pytest.raises(service.KnowledgeInputError, match="exceeds 10 characters"):
        await service.ingest_document(
            db_session,
            text="x" * 11,
            max_chars=10,
            max_chunks=10_000,
            embed_deadline_s=None,
            **common,
        )
    with pytest.raises(service.KnowledgeInputError, match="must not be empty"):
        await service.ingest_document(
            db_session,
            text="   \n",
            max_chars=10,
            max_chunks=10_000,
            embed_deadline_s=None,
            **common,
        )


async def test_service_dedupes_identical_text(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    kwargs = {
        "org_id": dev_org_id,
        "project_id": None,
        "title": "t",
        "source": "upload",
        "text": RUNBOOK,
        "created_by": None,
        "embedder": HashingEmbedder(),
        "max_chars": 100_000,
        "max_chunks": 10_000,
        "embed_deadline_s": None,
    }
    first, created_first = await service.ingest_document(db_session, **kwargs)
    second, created_second = await service.ingest_document(db_session, **kwargs)
    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert first.chunk_count >= 1


# ── Routes: happy path ────────────────────────────────────────────────────────


async def test_create_get_list_delete_happy_path(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Knowledge Org")

    created = await _post_doc(client, org_id)
    assert created.status_code == 201
    doc = created.json()
    assert doc["org_id"] == org_id
    assert doc["status"] == "ready"
    assert doc["source"] == "upload"
    assert doc["chunk_count"] >= 1

    listed = await client.get(f"/v1/orgs/{org_id}/knowledge/documents")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [doc["id"]]

    fetched = await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert len(body["chunks"]) == doc["chunk_count"]
    assert [c["ordinal"] for c in body["chunks"]] == list(range(doc["chunk_count"]))
    assert "kubectl rollout undo" in "".join(c["text"] for c in body["chunks"])

    deleted = await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    assert deleted.status_code == 204
    assert (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    ).status_code == 404


async def test_embeddings_never_in_responses(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Embed Org")
    doc = (await _post_doc(client, org_id)).json()

    fetched = (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    ).json()
    listed = (await client.get(f"/v1/orgs/{org_id}/knowledge/documents")).json()
    assert "embedding" not in _walk_keys(fetched)
    assert "embedding" not in _walk_keys(listed)


async def test_repost_identical_text_returns_200_with_same_document(
    client: AsyncClient,
) -> None:
    org_id = await _create_org(client, "Dedupe Org")
    first = await _post_doc(client, org_id)
    second = await _post_doc(client, org_id, title="Renamed")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["title"] == "Runbook"
    assert len((await client.get(f"/v1/orgs/{org_id}/knowledge/documents")).json()) == 1


async def test_list_orders_newest_first_and_paginates(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _create_org(client, "Order Org")
    older = (
        await _post_doc(client, org_id, text="older body text", title="old")
    ).json()
    newer = (
        await _post_doc(client, org_id, text="newer body text", title="new")
    ).json()
    await db_session.execute(
        update(KnowledgeDocument)
        .where(KnowledgeDocument.id == uuid.UUID(older["id"]))
        .values(created_at=datetime.now(UTC) - timedelta(days=1))
    )
    await db_session.commit()

    listed = (await client.get(f"/v1/orgs/{org_id}/knowledge/documents")).json()
    assert [d["id"] for d in listed] == [newer["id"], older["id"]]

    page = (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents?limit=1&offset=1")
    ).json()
    assert [d["id"] for d in page] == [older["id"]]


async def test_list_filters_by_project(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Filter Org")
    proj = (
        await client.post(f"/v1/orgs/{org_id}/projects", json={"name": "Alpha"})
    ).json()
    in_project = (
        await _post_doc(client, org_id, project_id=proj["id"], text="project text")
    ).json()
    (await _post_doc(client, org_id, text="org-wide text")).json()

    filtered = (
        await client.get(
            f"/v1/orgs/{org_id}/knowledge/documents?project_id={proj['id']}"
        )
    ).json()
    assert [d["id"] for d in filtered] == [in_project["id"]]


async def test_delete_cascades_to_chunks(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    org_id = await _create_org(client, "Cascade Org")
    doc = (await _post_doc(client, org_id)).json()
    before = (await db_session.execute(select(KnowledgeChunk))).scalars().all()
    assert len(before) == doc["chunk_count"]

    await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    db_session.expire_all()
    after = (await db_session.execute(select(KnowledgeChunk))).scalars().all()
    assert after == []


# ── Routes: validation ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"text": ""},
        {"text": "   \n\t"},
        {"title": ""},
        {"title": "x" * 301},
        {"source": ""},
        {"source": "x" * 41},
    ],
)
async def test_create_rejects_invalid_body(
    client: AsyncClient, overrides: dict
) -> None:
    org_id = await _create_org(client, "Validation Org")
    resp = await _post_doc(client, org_id, **overrides)
    assert resp.status_code == 422


async def test_create_rejects_project_from_another_org(client: AsyncClient) -> None:
    org_a = await _create_org(client, "Org A")
    org_b = await _create_org(client, "Org B")
    foreign = (
        await client.post(f"/v1/orgs/{org_b}/projects", json={"name": "Bee"})
    ).json()
    resp = await _post_doc(client, org_a, project_id=foreign["id"])
    assert resp.status_code == 404


# ── Routes: permissions and tenancy ───────────────────────────────────────────


async def test_viewer_can_read_but_not_write(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Viewer Org")
    doc = (await _post_doc(client, org_id)).json()
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id)
        .values(role="viewer")
    )
    await db_session.commit()

    assert (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents")
    ).status_code == 200
    assert (await _post_doc(client, org_id, text="new text")).status_code == 403
    assert (
        await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    ).status_code == 403


async def test_member_can_create_but_not_delete(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Member Org")
    doc = (await _post_doc(client, org_id)).json()
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id)
        .values(role="member")
    )
    await db_session.commit()

    assert (await _post_doc(client, org_id, text="another text")).status_code == 201
    assert (
        await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    ).status_code == 403


async def test_non_member_is_forbidden(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Stranger Org")
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id)
        .values(role="viewer")
    )
    await db_session.execute(
        delete(OrgMember).where(
            OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == dev_user_id
        )
    )
    await db_session.commit()

    assert (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents")
    ).status_code == 403
    assert (await _post_doc(client, org_id)).status_code == 403


async def test_cross_org_document_is_not_found(client: AsyncClient) -> None:
    org_a = await _create_org(client, "Tenant A")
    org_b = await _create_org(client, "Tenant B")
    doc_b = (await _post_doc(client, org_b)).json()

    fetched = await client.get(f"/v1/orgs/{org_a}/knowledge/documents/{doc_b['id']}")
    assert fetched.status_code == 404
    assert "Runbook" not in fetched.text

    deleted = await client.delete(f"/v1/orgs/{org_a}/knowledge/documents/{doc_b['id']}")
    assert deleted.status_code == 404

    still_there = await client.get(
        f"/v1/orgs/{org_b}/knowledge/documents/{doc_b['id']}"
    )
    assert still_there.status_code == 200


async def test_cross_org_list_does_not_leak(client: AsyncClient) -> None:
    org_a = await _create_org(client, "Leak A")
    org_b = await _create_org(client, "Leak B")
    await _post_doc(client, org_b, text="secret tenant b text")

    assert (await client.get(f"/v1/orgs/{org_a}/knowledge/documents")).json() == []


async def test_missing_document_is_404(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Missing Org")
    missing = uuid.uuid4()
    assert (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{missing}")
    ).status_code == 404
    assert (
        await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{missing}")
    ).status_code == 404


# ── Review fixes ──────────────────────────────────────────────────────────────


class _DelayedEmbedder(HashingEmbedder):
    def __init__(self, delay_s: float) -> None:
        super().__init__()
        self._delay_s = delay_s

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(self._delay_s)
        return await super().embed(texts)


async def _make_project(client: AsyncClient, org_id: str, name: str) -> str:
    resp = await client.post(f"/v1/orgs/{org_id}/projects", json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _set_org_role(
    db_session: AsyncSession, org_id: str, user_id: uuid.UUID, role: str
) -> None:
    await db_session.execute(
        update(OrgMember)
        .where(OrgMember.org_id == uuid.UUID(org_id), OrgMember.user_id == user_id)
        .values(role=role)
    )
    await db_session.commit()


async def _set_override(
    db_session: AsyncSession, project_id: str, user_id: uuid.UUID, role: str
) -> None:
    db_session.add(
        ProjectRoleOverride(
            project_id=uuid.UUID(project_id), user_id=user_id, role=role
        )
    )
    await db_session.commit()


# I2: no transaction is open while the embedder runs.


async def test_embedding_runs_with_no_open_transaction(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    seen: dict[str, bool] = {}

    class _Probe(HashingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            seen["in_transaction"] = db_session.in_transaction()
            return await super().embed(texts)

    await service.ingest_document(
        db_session,
        org_id=dev_org_id,
        project_id=None,
        title="t",
        source="upload",
        text=RUNBOOK,
        created_by=None,
        embedder=_Probe(),
        max_chars=100_000,
        max_chunks=10_000,
        embed_deadline_s=None,
    )
    assert seen == {"in_transaction": False}


# I2: a deadline stops a slow embedder and leaves nothing behind.


async def test_embedding_deadline_raises_and_writes_nothing(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    with pytest.raises(EmbeddingError, match="deadline"):
        await service.ingest_document(
            db_session,
            org_id=dev_org_id,
            project_id=None,
            title="t",
            source="upload",
            text=RUNBOOK,
            created_by=None,
            embedder=_DelayedEmbedder(1.0),
            max_chars=100_000,
            max_chunks=10_000,
            embed_deadline_s=0.01,
        )
    assert (await db_session.execute(select(KnowledgeDocument))).scalars().all() == []


async def test_route_maps_deadline_to_503(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Deadline Org")
    monkeypatch.setattr(
        knowledge_routes,
        "get_settings",
        lambda: Settings(knowledge_embedding_deadline_seconds=0.01),
    )
    app.dependency_overrides[get_embedder] = lambda: _DelayedEmbedder(1.0)
    resp = await _post_doc(client, org_id)
    assert resp.status_code == 503


# M1: embedder failure is a clean 503 with no upstream detail.


async def test_route_maps_embedder_failure_to_503_without_detail(
    client: AsyncClient,
) -> None:
    class _Broken(HashingEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise EmbeddingError("upstream https://internal.example key=SECRET123")

    org_id = await _create_org(client, "Broken Embedder Org")
    app.dependency_overrides[get_embedder] = lambda: _Broken()
    resp = await _post_doc(client, org_id)
    assert resp.status_code == 503
    assert "internal.example" not in resp.text
    assert "SECRET123" not in resp.text


# I3: chunk limits and paging.


async def test_service_rejects_more_chunks_than_allowed(
    db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    with pytest.raises(service.KnowledgeInputError, match="more than 2 chunks"):
        await service.ingest_document(
            db_session,
            org_id=dev_org_id,
            project_id=None,
            title="t",
            source="upload",
            text="word " * 1000,
            created_by=None,
            embedder=HashingEmbedder(),
            max_chars=100_000,
            max_chunks=2,
            embed_deadline_s=None,
        )


async def test_route_returns_422_when_document_has_too_many_chunks(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id = await _create_org(client, "Chunk Limit Org")
    monkeypatch.setattr(
        knowledge_routes, "get_settings", lambda: Settings(knowledge_max_chunks=2)
    )
    resp = await _post_doc(client, org_id, text="word " * 1000)
    assert resp.status_code == 422


async def test_document_detail_pages_its_chunks(client: AsyncClient) -> None:
    org_id = await _create_org(client, "Paging Org")
    text = "".join(f"## s{i}\n\n" + "word " * 200 + "\n\n" for i in range(10))
    doc = (await _post_doc(client, org_id, text=text)).json()
    total = doc["chunk_count"]
    assert total >= 4

    url = f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}"
    page = (await client.get(f"{url}?chunk_limit=2&chunk_offset=1")).json()
    assert [c["ordinal"] for c in page["chunks"]] == [1, 2]
    assert page["chunk_count"] == total

    default_page = (await client.get(url)).json()
    assert len(default_page["chunks"]) == min(total, 100)

    assert (await client.get(f"{url}?chunk_limit=0")).status_code == 422
    assert (await client.get(f"{url}?chunk_limit=501")).status_code == 422


# M2: NUL bytes and lone surrogates are rejected before they reach the database.


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "bad\x00title"),
        ("text", "ok\x00"),
        ("text", "\ud800"),
        ("title", "\udfff"),
    ],
)
def test_schema_rejects_nul_and_lone_surrogates(field: str, value: str) -> None:
    payload = {"title": "t", "source": "upload", "text": "body"}
    payload[field] = value
    with pytest.raises(ValidationError):
        KnowledgeDocumentCreate(**payload)


async def test_route_rejects_nul_and_lone_surrogate_with_422(
    client: AsyncClient,
) -> None:
    org_id = await _create_org(client, "Unsafe Text Org")
    assert (await _post_doc(client, org_id, text="a\x00b")).status_code == 422
    # httpx cannot encode a lone surrogate, so send the JSON escape a client would.
    raw = b'{"title":"t","source":"upload","text":"\\ud800"}'
    resp = await client.post(
        f"/v1/orgs/{org_id}/knowledge/documents",
        content=raw,
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422


# I1: project role overrides are honoured on create, read and delete.


async def test_viewer_override_blocks_admin_in_that_project(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Override Lower Org")
    project_id = await _make_project(client, org_id, "Lowered")
    in_project = (
        await _post_doc(client, org_id, project_id=project_id, text="p doc")
    ).json()

    await _set_org_role(db_session, org_id, dev_user_id, "admin")
    await _set_override(db_session, project_id, dev_user_id, "viewer")

    assert (
        await _post_doc(client, org_id, project_id=project_id, text="new p doc")
    ).status_code == 403
    assert (
        await client.delete(f"/v1/orgs/{org_id}/knowledge/documents/{in_project['id']}")
    ).status_code == 403
    assert (
        await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{in_project['id']}")
    ).status_code == 200
    # Org-level documents still follow the org role.
    assert (await _post_doc(client, org_id, text="org-wide doc")).status_code == 201


async def test_member_override_allows_viewer_in_that_project(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Override Raise Org")
    project_id = await _make_project(client, org_id, "Raised")

    await _set_org_role(db_session, org_id, dev_user_id, "viewer")
    await _set_override(db_session, project_id, dev_user_id, "member")

    assert (
        await _post_doc(client, org_id, project_id=project_id, text="raised doc")
    ).status_code == 201
    # Without the override the viewer still cannot write org-level documents.
    assert (await _post_doc(client, org_id, text="org doc")).status_code == 403


async def test_viewer_without_override_cannot_write_into_project(
    client: AsyncClient, db_session: AsyncSession, dev_user_id: uuid.UUID
) -> None:
    org_id = await _create_org(client, "Plain Viewer Org")
    project_id = await _make_project(client, org_id, "Plain")
    await _set_org_role(db_session, org_id, dev_user_id, "viewer")
    assert (await _post_doc(client, org_id, project_id=project_id)).status_code == 403


async def test_project_filter_on_list_checks_project_membership(
    client: AsyncClient,
) -> None:
    org_a = await _create_org(client, "Filter Org A")
    org_b = await _create_org(client, "Filter Org B")
    foreign_project = await _make_project(client, org_b, "Foreign")
    resp = await client.get(
        f"/v1/orgs/{org_a}/knowledge/documents?project_id={foreign_project}"
    )
    assert resp.status_code == 404


# I4: dedupe is scoped to the project.


async def test_same_text_in_two_projects_creates_two_documents(
    client: AsyncClient,
) -> None:
    org_id = await _create_org(client, "Two Projects Org")
    p1 = await _make_project(client, org_id, "P1")
    p2 = await _make_project(client, org_id, "P2")
    first = await _post_doc(client, org_id, project_id=p1, text="shared text")
    second = await _post_doc(client, org_id, project_id=p2, text="shared text")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


async def test_same_text_twice_in_one_project_dedupes(client: AsyncClient) -> None:
    org_id = await _create_org(client, "One Project Org")
    p1 = await _make_project(client, org_id, "Only")
    first = await _post_doc(client, org_id, project_id=p1, text="repeat text")
    second = await _post_doc(client, org_id, project_id=p1, text="repeat text")
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


# Test gaps: rollback after a flush, and the IntegrityError race path.


async def test_failure_after_flush_leaves_no_document(
    db_session: AsyncSession, dev_org_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_commit = db_session.commit
    calls = {"n": 0}

    async def commit_then_fail() -> None:
        calls["n"] += 1
        if calls["n"] == 1:  # the pre-embedding commit
            await real_commit()
            return
        raise RuntimeError("boom after flush")

    monkeypatch.setattr(db_session, "commit", commit_then_fail)
    with pytest.raises(RuntimeError, match="boom after flush"):
        await service.ingest_document(
            db_session,
            org_id=dev_org_id,
            project_id=None,
            title="t",
            source="upload",
            text=RUNBOOK,
            created_by=None,
            embedder=HashingEmbedder(),
            max_chars=100_000,
            max_chunks=10_000,
            embed_deadline_s=None,
        )
    assert (await db_session.execute(select(KnowledgeDocument))).scalars().all() == []
    assert (await db_session.execute(select(KnowledgeChunk))).scalars().all() == []


async def test_integrity_race_returns_the_winning_document(
    db_session: AsyncSession, dev_org_id: uuid.UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    # SQLite treats NULLs as distinct in unique constraints, so use a real project.
    project = Project(
        org_id=dev_org_id, name="Race", slug=f"race-{uuid.uuid4().hex[:8]}"
    )
    db_session.add(project)
    await db_session.commit()

    kwargs = {
        "org_id": dev_org_id,
        "project_id": project.id,
        "title": "t",
        "source": "upload",
        "text": RUNBOOK,
        "created_by": None,
        "embedder": HashingEmbedder(),
        "max_chars": 100_000,
        "max_chunks": 10_000,
        "embed_deadline_s": None,
    }
    original, created = await service.ingest_document(db_session, **kwargs)
    assert created is True

    real_find = service._find_existing
    calls = {"n": 0}

    async def first_lookup_misses(
        *args: object, **kw: object
    ) -> KnowledgeDocument | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return await real_find(*args, **kw)

    monkeypatch.setattr(service, "_find_existing", first_lookup_misses)
    winner, created_again = await service.ingest_document(db_session, **kwargs)

    assert created_again is False
    assert winner.id == original.id
    # The session is still usable after the rollback.
    count = (
        await db_session.execute(select(func.count()).select_from(KnowledgeDocument))
    ).scalar_one()
    assert count == 1
