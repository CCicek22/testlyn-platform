"""Smoke tests for Phase 4 product scaffolds.

Each product's POST endpoint must return 501 NOT_IMPLEMENTED.
Each product's runner must declare the correct product discriminator,
raise RunnerNotAvailable on launch, and return safely from cancel/status.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from testlyn_api.core.runner import RunnerNotAvailable

# ---------------------------------------------------------------------------
# Runner protocol conformance
# ---------------------------------------------------------------------------


class TestPhase4RunnerDiscriminators:
    @pytest.mark.parametrize(
        "module_path, class_name, expected_product",
        [
            ("testlyn_api.products.mobile.runner", "MobileRunner", "mobile"),
            ("testlyn_api.products.visual.runner", "VisualRunner", "visual"),
            ("testlyn_api.products.rum.runner", "RumRunner", "rum"),
            ("testlyn_api.products.tdm.runner", "TdmRunner", "tdm"),
            ("testlyn_api.products.qa_maturity.runner", "QaMaturityRunner", "qa_maturity"),
            ("testlyn_api.products.eng_analytics.runner", "EngAnalyticsRunner", "eng_analytics"),
            ("testlyn_api.products.cicd_insights.runner", "CicdInsightsRunner", "cicd_insights"),
        ],
    )
    def test_product_discriminator(
        self, module_path: str, class_name: str, expected_product: str
    ) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        assert cls.product == expected_product

    @pytest.mark.parametrize(
        "module_path, class_name",
        [
            ("testlyn_api.products.mobile.runner", "MobileRunner"),
            ("testlyn_api.products.visual.runner", "VisualRunner"),
            ("testlyn_api.products.rum.runner", "RumRunner"),
            ("testlyn_api.products.tdm.runner", "TdmRunner"),
            ("testlyn_api.products.qa_maturity.runner", "QaMaturityRunner"),
            ("testlyn_api.products.eng_analytics.runner", "EngAnalyticsRunner"),
            ("testlyn_api.products.cicd_insights.runner", "CicdInsightsRunner"),
        ],
    )
    @pytest.mark.asyncio
    async def test_launch_raises_runner_not_available(
        self, module_path: str, class_name: str
    ) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        runner = cls()
        with pytest.raises(RunnerNotAvailable):
            await runner.launch(
                test_run_id=uuid.uuid4(),
                script_uri="",
                vus=1,
                duration_seconds=60,
                env={},
            )

    @pytest.mark.parametrize(
        "module_path, class_name",
        [
            ("testlyn_api.products.mobile.runner", "MobileRunner"),
            ("testlyn_api.products.visual.runner", "VisualRunner"),
            ("testlyn_api.products.rum.runner", "RumRunner"),
            ("testlyn_api.products.tdm.runner", "TdmRunner"),
            ("testlyn_api.products.qa_maturity.runner", "QaMaturityRunner"),
            ("testlyn_api.products.eng_analytics.runner", "EngAnalyticsRunner"),
            ("testlyn_api.products.cicd_insights.runner", "CicdInsightsRunner"),
        ],
    )
    @pytest.mark.asyncio
    async def test_cancel_returns_safely(
        self, module_path: str, class_name: str
    ) -> None:
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        runner = cls()
        # cancel must not raise
        await runner.cancel(runner_id="stub-id")

    @pytest.mark.parametrize(
        "module_path, class_name",
        [
            ("testlyn_api.products.mobile.runner", "MobileRunner"),
            ("testlyn_api.products.visual.runner", "VisualRunner"),
            ("testlyn_api.products.rum.runner", "RumRunner"),
            ("testlyn_api.products.tdm.runner", "TdmRunner"),
            ("testlyn_api.products.qa_maturity.runner", "QaMaturityRunner"),
            ("testlyn_api.products.eng_analytics.runner", "EngAnalyticsRunner"),
            ("testlyn_api.products.cicd_insights.runner", "CicdInsightsRunner"),
        ],
    )
    @pytest.mark.asyncio
    async def test_status_raises_not_implemented(
        self, module_path: str, class_name: str
    ) -> None:
        import importlib

        from testlyn_api.core.runner import RunnerStatus

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        runner = cls()
        result = await runner.status(runner_id="stub-id")
        assert isinstance(result, RunnerStatus)
        assert result.state == "unavailable"


# ---------------------------------------------------------------------------
# API route smoke tests — all POST endpoints must return 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mobile_create_run_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/mobile/runs",
        json={
            "org_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"
    assert data["available_in"] == "Phase 4 GA"


@pytest.mark.asyncio
async def test_mobile_get_run_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/mobile/runs/{uuid.uuid4()}")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_visual_create_scan_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/visual/scans",
        json={
            "org_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "baseline_uri": "gs://bucket/baseline.png",
            "current_uri": "gs://bucket/current.png",
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_visual_get_scan_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/visual/scans/{uuid.uuid4()}")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_rum_register_site_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/rum/sites",
        json={
            "org_id": str(uuid.uuid4()),
            "target_id": str(uuid.uuid4()),
            "origin": "https://example.com",
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_rum_get_pageviews_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/rum/sites/{uuid.uuid4()}/pageviews")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_tdm_create_subset_job_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/tdm/subset-jobs",
        json={
            "org_id": str(uuid.uuid4()),
            "dsn_secret_id": "projects/test/secrets/db-dsn/versions/latest",
            "tables": ["users", "orders"],
            "output_bucket": "testlyn-prod-spool",
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_tdm_get_subset_job_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/tdm/subset-jobs/{uuid.uuid4()}")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_qa_maturity_create_assessment_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/qa-maturity/assessments",
        json={
            "org_id": str(uuid.uuid4()),
            "answers": {"q1": "yes", "q2": "partial"},
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_qa_maturity_get_assessment_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/qa-maturity/assessments/{uuid.uuid4()}")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_eng_analytics_create_connection_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/eng-analytics/connections",
        json={
            "org_id": str(uuid.uuid4()),
            "provider": "github",
            "config": {"repo": "CCicek22/testlyn"},
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_eng_analytics_get_connection_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/eng-analytics/connections/{uuid.uuid4()}")
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_cicd_insights_ingest_run_returns_501(client: AsyncClient) -> None:
    response = await client.post(
        "/v1/products/cicd-insights/runs",
        json={
            "org_id": str(uuid.uuid4()),
            "pipeline_id": "pipeline-abc-123",
            "duration_ms": 120_000,
            "flaky_test_count": 2,
            "cost_estimate_usd": 0.42,
        },
    )
    assert response.status_code == 501
    data = response.json()
    assert data["code"] == "NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_cicd_insights_get_run_returns_501(client: AsyncClient) -> None:
    response = await client.get(f"/v1/products/cicd-insights/runs/{uuid.uuid4()}")
    assert response.status_code == 501
