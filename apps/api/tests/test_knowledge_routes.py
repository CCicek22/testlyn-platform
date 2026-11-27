"""Knowledge store: ingestion service and /v1/orgs/{org_id}/knowledge routes (SQLite)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from testlyn_api.knowledge import service
from testlyn_api.knowledge.embeddings import EmbeddingError, HashingEmbedder
from testlyn_api.models.knowledge import KnowledgeChunk, KnowledgeDocument
from testlyn_api.models.org import OrgMember

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
        await service.ingest_document(db_session, text="x" * 11, max_chars=10, **common)
    with pytest.raises(service.KnowledgeInputError, match="must not be empty"):
        await service.ingest_document(db_session, text="   \n", max_chars=10, **common)


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
    assert doc["chunk_count"] >= 2

    listed = await client.get(f"/v1/orgs/{org_id}/knowledge/documents")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [doc["id"]]

    fetched = await client.get(f"/v1/orgs/{org_id}/knowledge/documents/{doc['id']}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert len(body["chunks"]) == doc["chunk_count"]
    assert [c["ordinal"] for c in body["chunks"]] == list(range(doc["chunk_count"]))
    assert "Runbook > Rollback" in {c["heading"] for c in body["chunks"]}

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
