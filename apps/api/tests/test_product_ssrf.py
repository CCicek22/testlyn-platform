"""SSRF guard on the browser/scanner product routes.

Covers finding #3 (Codex review 2026-05-25): the a11y, api-contract, and
security scan routes accept arbitrary user URLs that are fetched from inside the
worker network. Each route must reject private/loopback/link-local/reserved/
metadata targets with 422 *before* enqueueing a job, while still accepting
public URLs.
"""

from __future__ import annotations

import socket
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# URLs that must be rejected. IP literals resolve to themselves (no network),
# and the metadata hostname is blocked before any DNS lookup, so these cases are
# hermetic and do not require mocking socket.getaddrinfo.
_UNSAFE_URLS = [
    "http://127.0.0.1/",
    "http://10.0.0.5/",
    "http://192.168.1.1/",
    "http://169.254.169.254/computeMetadata/v1/",
    "http://metadata.google.internal/",
]


def _public_addrinfo(ip: str = "93.184.216.34", port: int = 443):
    """getaddrinfo()-shaped result pinning a host to a single public IPv4."""
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


async def _seed_a11y_run(session: AsyncSession, org_id: uuid.UUID) -> str:
    """Seed a run owned by ``org_id`` so the a11y route's perm check passes."""
    from testlyn_api.models.project import Project
    from testlyn_api.models.test import Test as TestModel
    from testlyn_api.models.test_run import TestRun as TestRunModel

    project = Project(org_id=org_id, name="P", slug=f"p-{uuid.uuid4().hex[:6]}")
    session.add(project)
    await session.flush()
    test = TestModel(project_id=project.id, name="T", script_inline="x")
    session.add(test)
    await session.flush()
    run = TestRunModel(test_id=test.id, product="a11y")
    session.add(run)
    await session.flush()
    run_id = str(run.id)
    await session.commit()
    return run_id


# ─── a11y ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("url", _UNSAFE_URLS)
async def test_a11y_audit_rejects_unsafe_url(
    client: AsyncClient, db_session: AsyncSession, dev_org_id: uuid.UUID, url: str
) -> None:
    run_id = await _seed_a11y_run(db_session, dev_org_id)
    resp = await client.post(
        "/v1/products/a11y/audit",
        json={"test_run_id": run_id, "config": {"urls": [url], "max_depth": 1}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "target URL is not allowed"


@pytest.mark.asyncio
async def test_a11y_audit_allows_public_url(
    client: AsyncClient, db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    run_id = await _seed_a11y_run(db_session, dev_org_id)
    with patch("socket.getaddrinfo", return_value=_public_addrinfo()):
        resp = await client.post(
            "/v1/products/a11y/audit",
            json={
                "test_run_id": run_id,
                "config": {"urls": ["https://example.com"], "max_depth": 1},
            },
        )
    assert resp.status_code == 202


# ─── api-contract ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("url", _UNSAFE_URLS)
async def test_api_contract_rejects_unsafe_target_url(
    client: AsyncClient, dev_org_id: uuid.UUID, url: str
) -> None:
    resp = await client.post(
        "/v1/products/api-contract/scan",
        json={
            "org_id": str(dev_org_id),
            "openapi_url": "https://example.com/openapi.json",
            "target_url": url,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "target URL is not allowed"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", _UNSAFE_URLS)
async def test_api_contract_rejects_unsafe_openapi_url(
    client: AsyncClient, dev_org_id: uuid.UUID, url: str
) -> None:
    resp = await client.post(
        "/v1/products/api-contract/scan",
        json={
            "org_id": str(dev_org_id),
            "openapi_url": url,
            "target_url": "https://example.com",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "target URL is not allowed"


@pytest.mark.asyncio
async def test_api_contract_allows_public_urls(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    with (
        patch("shutil.which", return_value=None),
        patch("socket.getaddrinfo", return_value=_public_addrinfo()),
    ):
        resp = await client.post(
            "/v1/products/api-contract/scan",
            json={
                "org_id": str(dev_org_id),
                "openapi_url": "https://example.com/openapi.json",
                "target_url": "https://example.com",
            },
        )
    assert resp.status_code == 202


# ─── security ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("url", _UNSAFE_URLS)
async def test_security_scan_rejects_unsafe_url(
    client: AsyncClient, dev_org_id: uuid.UUID, url: str
) -> None:
    resp = await client.post(
        "/v1/products/security/scan",
        json={"org_id": str(dev_org_id), "target_url": url, "scan_kind": "baseline"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "target URL is not allowed"


@pytest.mark.asyncio
async def test_security_scan_allows_public_url(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    with (
        patch("shutil.which", return_value=None),
        patch("socket.getaddrinfo", return_value=_public_addrinfo()),
    ):
        resp = await client.post(
            "/v1/products/security/scan",
            json={
                "org_id": str(dev_org_id),
                "target_url": "https://example.com",
                "scan_kind": "baseline",
            },
        )
    assert resp.status_code == 202
