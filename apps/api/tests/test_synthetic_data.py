from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# SyntheticDataRunner — Protocol conformance
# ---------------------------------------------------------------------------


class TestSyntheticDataRunnerProtocol:
    def test_implements_runner_protocol(self) -> None:
        from testlyn_api.core.runner import Runner
        from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

        runner = SyntheticDataRunner()
        assert isinstance(runner, Runner)

    def test_product_discriminator(self) -> None:
        from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

        assert SyntheticDataRunner.product == "synthetic_data"

    @pytest.mark.asyncio
    async def test_launch_docker_returns_stub(self) -> None:
        from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

        runner = SyntheticDataRunner()
        run_id = uuid.uuid4()
        result = await runner.launch(
            test_run_id=run_id,
            script_uri="",
            vus=1,
            duration_seconds=60,
            env={"DSN_SECRET_ID": "test-secret"},
        )
        assert result.runner_id.startswith("synth-docker-stub-")
        assert result.region == "local"

    @pytest.mark.asyncio
    async def test_cancel_docker_noop(self) -> None:
        from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

        runner = SyntheticDataRunner()
        await runner.cancel(runner_id="synth-docker-stub-abc")

    @pytest.mark.asyncio
    async def test_status_docker_returns_running(self) -> None:
        from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

        runner = SyntheticDataRunner()
        status = await runner.status(runner_id="synth-docker-stub-abc")
        assert status.state == "running"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestGenerateSchemas:
    def test_defaults(self) -> None:
        from testlyn_api.products.synthetic_data.schemas import GenerateRequest

        req = GenerateRequest(
            org_id=uuid.uuid4(),
            dsn_secret_id="projects/proj/secrets/dsn/versions/latest",
        )
        assert req.row_count == 100
        assert req.output_mode == "gcs"
        assert req.schema_overrides == {}
        assert req.gdpr_masking_rules == {}

    def test_row_count_bounds(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.synthetic_data.schemas import GenerateRequest

        with pytest.raises(ValidationError):
            GenerateRequest(
                org_id=uuid.uuid4(),
                dsn_secret_id="s",
                row_count=0,
            )
        with pytest.raises(ValidationError):
            GenerateRequest(
                org_id=uuid.uuid4(),
                dsn_secret_id="s",
                row_count=200_000,
            )

    def test_response_product_literal(self) -> None:
        from testlyn_api.products.synthetic_data.schemas import GenerateResponse

        resp = GenerateResponse(job_id=uuid.uuid4())
        assert resp.product == "synthetic_data"
        assert resp.status == "queued"


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_202(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    org_id = str(dev_org_id)
    response = await client.post(
        "/v1/products/synthetic-data/generate",
        json={
            "org_id": org_id,
            "dsn_secret_id": "projects/proj/secrets/dsn/versions/latest",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["product"] == "synthetic_data"
    # A real TestRun row is created and transitioned on launch now.
    assert data["status"] == "running"
    assert "job_id" in data
    # stub mode always has a GCS URI
    assert data["dump_gcs_uri"] is not None
    assert data["dump_gcs_uri"].startswith("gs://")


@pytest.mark.asyncio
async def test_generate_with_overrides(client: AsyncClient, dev_org_id: uuid.UUID) -> None:
    response = await client.post(
        "/v1/products/synthetic-data/generate",
        json={
            "org_id": str(dev_org_id),
            "dsn_secret_id": "secret-id",
            "schema_overrides": {"users": {"email": "email"}},
            "gdpr_masking_rules": {"users.phone": "mask"},
            "row_count": 500,
            "output_mode": "insert",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "running"


# ---------------------------------------------------------------------------
# Cloud launch env (review finding: INTERNAL_TOKEN was missing → callbacks 403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_launch_cloud_env_includes_internal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from google.cloud import run_v2

    from testlyn_api.products.synthetic_data import runner as runner_mod

    class _FakeOp:
        metadata = SimpleNamespace(name="projects/p/locations/r/jobs/j/executions/e")

    captured: dict = {}

    class _FakeJobs:
        def __init__(self, *a, **k):  # noqa: ANN002, ANN003
            pass

        async def run_job(self, request=None, **_k):  # noqa: ANN001, ANN003
            captured["request"] = request
            return _FakeOp()

    monkeypatch.setattr(
        runner_mod,
        "get_settings",
        lambda: SimpleNamespace(
            run_mode="cloud",
            gcp_project_id="test-project",
            gcp_region="us-central1",
            gcs_results_bucket="test-results",
            api_base_url="http://testserver",
            internal_token="secret-tok",
        ),
    )
    monkeypatch.setattr(run_v2, "JobsAsyncClient", _FakeJobs)

    from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner

    await SyntheticDataRunner()._launch_cloud(
        test_run_id=uuid.uuid4(),
        env={"DSN_SECRET_ID": "s"},
    )

    co = captured["request"].overrides.container_overrides[0]
    env = {e.name: e.value for e in co.env}
    assert env["INTERNAL_TOKEN"] == "secret-tok"
    assert "CALLBACK_URL" in env


# ---------------------------------------------------------------------------
# Migration smoke test
# ---------------------------------------------------------------------------


def _load_migration_0009():
    if "alembic.op" not in sys.modules:
        sys.modules["alembic.op"] = MagicMock()
    alembic_mod = sys.modules.get("alembic")
    if alembic_mod is not None and not hasattr(alembic_mod, "op"):
        alembic_mod.op = MagicMock()

    path = (
        pathlib.Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "0009_phase3_products.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0009", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod


class TestMigration0009:
    def test_revision_chain(self) -> None:
        m = _load_migration_0009()
        assert m.revision == "0009"
        assert m.down_revision == "0008"

    def test_has_upgrade_and_downgrade(self) -> None:
        m = _load_migration_0009()
        assert callable(m.upgrade)
        assert callable(m.downgrade)
