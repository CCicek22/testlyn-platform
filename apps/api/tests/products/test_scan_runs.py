"""Run-lifecycle tests for the ad-hoc product scan routes.

Review finding: security / api-contract / synthetic-data scan routes used to
mint a bare uuid4 with NO test_runs row, so the engine callback
``POST /v1/internal/runs/{id}/complete`` 404'd and no status endpoint existed.
These tests assert the full loop: POST scan → real TestRun row (correct
``product`` discriminator) → GET status → internal /complete transitions it.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.test_run import TestRun


async def _get_run(session: AsyncSession, run_id: str) -> TestRun | None:
    return (
        await session.execute(select(TestRun).where(TestRun.id == uuid.UUID(run_id)))
    ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_security_scan_creates_run_row(
    client: AsyncClient, db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    with patch("shutil.which", return_value=None):
        resp = await client.post(
            "/v1/products/security/scan",
            json={"org_id": str(dev_org_id), "target_url": "https://example.com"},
        )
    assert resp.status_code == 202
    scan_id = resp.json()["scan_id"]

    run = await _get_run(db_session, scan_id)
    assert run is not None, "scan must persist a real TestRun row"
    assert run.product == "security"
    assert run.state == "running"
    assert run.runner_id


@pytest.mark.asyncio
async def test_security_scan_status_endpoint(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    with patch("shutil.which", return_value=None):
        resp = await client.post(
            "/v1/products/security/scan",
            json={"org_id": str(dev_org_id), "target_url": "https://example.com"},
        )
    scan_id = resp.json()["scan_id"]

    status_resp = await client.get(f"/v1/products/security/scans/{scan_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["scan_id"] == scan_id
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_security_scan_complete_callback_transitions_run(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    """The engine callback must find the run and complete it (was a 404)."""
    with patch("shutil.which", return_value=None):
        resp = await client.post(
            "/v1/products/security/scan",
            json={"org_id": str(dev_org_id), "target_url": "https://example.com"},
        )
    scan_id = resp.json()["scan_id"]

    cb = await client.post(f"/v1/internal/runs/{scan_id}/complete", json={"exit_code": 0})
    assert cb.status_code == 200

    status_resp = await client.get(f"/v1/products/security/scans/{scan_id}")
    assert status_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_security_scan_status_404_unknown(client: AsyncClient) -> None:
    resp = await client.get(f"/v1/products/security/scans/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_contract_scan_creates_run_and_status(
    client: AsyncClient, db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    with patch("shutil.which", return_value=None):
        resp = await client.post(
            "/v1/products/api-contract/scan",
            json={
                "org_id": str(dev_org_id),
                "openapi_url": "https://example.com/openapi.json",
                "target_url": "https://example.com",
            },
        )
    assert resp.status_code == 202
    scan_id = resp.json()["scan_id"]

    run = await _get_run(db_session, scan_id)
    assert run is not None
    assert run.product == "api_contract"
    assert run.state == "running"

    status_resp = await client.get(f"/v1/products/api-contract/scans/{scan_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_synthetic_data_generate_creates_run_and_status(
    client: AsyncClient, db_session: AsyncSession, dev_org_id: uuid.UUID
) -> None:
    resp = await client.post(
        "/v1/products/synthetic-data/generate",
        json={"org_id": str(dev_org_id), "dsn_secret_id": "secret-id"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    run = await _get_run(db_session, job_id)
    assert run is not None
    assert run.product == "synthetic_data"
    assert run.state == "running"

    status_resp = await client.get(f"/v1/products/synthetic-data/jobs/{job_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_status_endpoint_product_scoped(
    client: AsyncClient, dev_org_id: uuid.UUID
) -> None:
    """A security run id queried via the api-contract endpoint → 404."""
    with patch("shutil.which", return_value=None):
        resp = await client.post(
            "/v1/products/security/scan",
            json={"org_id": str(dev_org_id), "target_url": "https://example.com"},
        )
    scan_id = resp.json()["scan_id"]

    cross = await client.get(f"/v1/products/api-contract/scans/{scan_id}")
    assert cross.status_code == 404
