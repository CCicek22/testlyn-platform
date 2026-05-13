from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

# Repo-root-relative paths — work on any machine, no absolute paths.
_ENGINE_A11Y = Path(__file__).resolve().parents[3] / "apps" / "engine-a11y"
_ENGINE = Path(__file__).resolve().parents[3] / "apps" / "engine"

# ---------------------------------------------------------------------------
# A11yRunner tests
# ---------------------------------------------------------------------------


class TestA11yRunnerProtocol:
    """Verify A11yRunner satisfies the Runner Protocol."""

    def test_implements_runner_protocol(self) -> None:
        from testlyn_api.core.runner import Runner
        from testlyn_api.products.a11y.runner import A11yRunner

        runner = A11yRunner()
        assert isinstance(runner, Runner)

    def test_product_discriminator(self) -> None:
        from testlyn_api.products.a11y.runner import A11yRunner

        assert A11yRunner.product == "a11y"

    @pytest.mark.asyncio
    async def test_launch_docker_returns_stub(self) -> None:
        """In docker mode, launch() returns a stub without touching Cloud Run."""
        from testlyn_api.products.a11y.runner import A11yRunner

        runner = A11yRunner()
        run_id = uuid.uuid4()

        result = await runner.launch(
            test_run_id=run_id,
            script_uri="",
            vus=1,
            duration_seconds=60,
            env={},
        )

        assert result.runner_id.startswith("a11y-docker-stub-")
        assert result.region == "local"

    @pytest.mark.asyncio
    async def test_cancel_docker_is_noop(self) -> None:
        from testlyn_api.products.a11y.runner import A11yRunner

        runner = A11yRunner()
        # Should not raise
        await runner.cancel(runner_id="a11y-docker-stub-abc")

    @pytest.mark.asyncio
    async def test_status_docker_returns_running(self) -> None:
        from testlyn_api.products.a11y.runner import A11yRunner

        runner = A11yRunner()
        status = await runner.status(runner_id="a11y-docker-stub-abc")
        assert status.state == "running"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestA11ySchemas:
    def test_audit_config_requires_urls(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.a11y.schemas import A11yAuditConfig

        with pytest.raises(ValidationError):
            A11yAuditConfig(urls=[])

    def test_audit_config_valid(self) -> None:
        from testlyn_api.products.a11y.schemas import A11yAuditConfig

        cfg = A11yAuditConfig(urls=["https://example.com"])
        assert len(cfg.urls) == 1
        assert cfg.max_depth == 1
        assert "wcag22aa" in cfg.wcag_tags

    def test_violation_impact_literals(self) -> None:
        from pydantic import ValidationError
        from testlyn_api.products.a11y.schemas import A11yViolation

        with pytest.raises(ValidationError):
            A11yViolation(
                rule_id="color-contrast",
                impact="catastrophic",  # not a valid literal
                html_snippet="<button>",
                dom_path="body > button",
                help_url="https://dequeuniversity.com/",
                target_url="https://example.com",
            )

    def test_valid_violation(self) -> None:
        from testlyn_api.products.a11y.schemas import A11yViolation

        v = A11yViolation(
            rule_id="color-contrast",
            impact="serious",
            html_snippet="<button style='color:white;background:white'>X</button>",
            dom_path="html > body > button",
            help_url="https://dequeuniversity.com/rules/axe/4.10/color-contrast",
            target_url="https://example.com",
        )
        assert v.impact == "serious"
        assert v.remediation is None

    def test_report_product_literal(self) -> None:
        from testlyn_api.products.a11y.schemas import A11yReport, A11ySummary

        report = A11yReport(
            run_id=uuid.uuid4(),
            summary=A11ySummary(total=0, critical=0, serious=0, moderate=0, minor=0),
            violations=[],
            created_at=datetime.now(tz=UTC),
        )
        assert report.product == "a11y"


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def patch_redis_for_remediation(monkeypatch):
    """Patch Redis to fakeredis for remediation tests."""
    import fakeredis.aioredis as fakeredis_async

    fake = fakeredis_async.FakeRedis(decode_responses=True)
    with patch("testlyn_api.core.cache.get_redis", return_value=fake):
        yield fake


class TestGenerateRemediation:
    @pytest.mark.asyncio
    async def test_fallback_on_missing_creds(self) -> None:
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            from testlyn_api.products.a11y import remediation

            result = await remediation.generate_remediation(
                rule_id="color-contrast",
                impact="serious",
                html_snippet="<button>X</button>",
                help_url="https://dequeuniversity.com/rules/axe/4.10/color-contrast",
            )

        assert "WCAG" in result or "wcag" in result.lower() or "color-contrast" in result

    @pytest.mark.asyncio
    async def test_fallback_contains_rule_id(self) -> None:
        import google.auth.exceptions

        with patch(
            "google.auth.default",
            side_effect=google.auth.exceptions.DefaultCredentialsError(),
        ):
            from testlyn_api.products.a11y import remediation

            result = await remediation.generate_remediation(
                rule_id="aria-label",
                impact="critical",
                html_snippet="<img src='logo.png'>",
                help_url="https://dequeuniversity.com/rules/axe/4.10/aria-label",
            )

        assert "aria-label" in result

    @pytest.mark.asyncio
    async def test_vertex_success_path(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "Add an alt attribute to the image element."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_creds = MagicMock()

        with (
            patch("google.auth.default", return_value=(mock_creds, "proj")),
            patch("google.cloud.aiplatform.init"),
            patch("vertexai.generative_models.GenerativeModel", return_value=mock_model),
        ):
            from importlib import reload

            from testlyn_api.products.a11y import remediation

            reload(remediation)

            result = await remediation.generate_remediation(
                rule_id="image-alt",
                impact="critical",
                html_snippet="<img src='logo.png'>",
                help_url="https://dequeuniversity.com/rules/axe/4.10/image-alt",
            )

        assert result == "Add an alt attribute to the image element."

    @pytest.mark.asyncio
    async def test_redis_cache_hit_skips_vertex(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "Cached remediation."
        mock_model = MagicMock()
        mock_model.generate_content_async = AsyncMock(return_value=mock_response)
        mock_creds = MagicMock()

        with (
            patch("google.auth.default", return_value=(mock_creds, "proj")),
            patch("google.cloud.aiplatform.init"),
            patch("vertexai.generative_models.GenerativeModel", return_value=mock_model),
        ):
            from importlib import reload

            from testlyn_api.products.a11y import remediation

            reload(remediation)

            snippet = "<img src='test.png'>"
            kwargs = dict(
                rule_id="image-alt",
                impact="critical",
                html_snippet=snippet,
                help_url="https://dequeuniversity.com/",
            )
            await remediation.generate_remediation(**kwargs)
            await remediation.generate_remediation(**kwargs)

        assert mock_model.generate_content_async.call_count == 1


# ---------------------------------------------------------------------------
# API routes (via test client)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_shot_audit_enqueued(client: AsyncClient) -> None:
    """POST /v1/products/a11y/audit returns 202 with runner_id."""
    run_id = str(uuid.uuid4())
    response = await client.post(
        "/v1/products/a11y/audit",
        json={
            "test_run_id": run_id,
            "config": {
                "urls": ["https://example.com"],
                "max_depth": 1,
            },
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["run_id"] == run_id
    assert "runner_id" in data
    assert data["runner_id"].startswith("a11y-docker-stub-")


@pytest.mark.asyncio
async def test_get_violations_stub(client: AsyncClient) -> None:
    """GET /v1/runs/:id/violations returns 200 with empty stub report."""
    run_id = str(uuid.uuid4())
    response = await client.get(f"/v1/runs/{run_id}/violations")
    assert response.status_code == 200
    data = response.json()
    assert data["product"] == "a11y"
    assert data["run_id"] == run_id
    assert data["summary"]["total"] == 0
    assert data["violations"] == []


# ---------------------------------------------------------------------------
# axe.py parser unit tests
# ---------------------------------------------------------------------------


class TestAxeParser:
    @pytest.fixture(autouse=True)
    def _inject_engine_a11y(self) -> None:
        """Ensure engine-a11y and engine (sidecar) are importable without absolute paths."""
        for p in (str(_ENGINE_A11Y), str(_ENGINE)):
            if p not in sys.path:
                sys.path.insert(0, p)

    def test_parse_valid_line(self) -> None:
        from parser.axe import parse_line

        line = '{"run_id":"abc","rule_id":"color-contrast","impact":"serious","html_snippet":"<button>X</button>","dom_path":"body > button","help_url":"https://dequeuniversity.com/","target_url":"https://example.com"}'
        event = parse_line(line)
        assert event is not None
        assert event.metric == "violation.serious"
        assert event.value == 1.0
        assert event.tags["severity"] == "serious"
        assert event.tags["rule_id"] == "color-contrast"

    @pytest.mark.parametrize(
        "impact",
        ["critical", "serious", "moderate", "minor"],
    )
    def test_all_valid_impacts(self, impact: str) -> None:
        from parser.axe import parse_line

        line = f'{{"run_id":"r1","rule_id":"rule","impact":"{impact}","html_snippet":"<x>","dom_path":"x","help_url":"http://h","target_url":"http://t"}}'
        event = parse_line(line)
        assert event is not None
        assert event.metric == f"violation.{impact}"

    def test_invalid_impact_returns_none(self) -> None:
        from parser.axe import parse_line

        line = '{"run_id":"r1","rule_id":"rule","impact":"catastrophic","html_snippet":"<x>","dom_path":"x","help_url":"http://h","target_url":"http://t"}'
        assert parse_line(line) is None

    def test_malformed_json_returns_none(self) -> None:
        from parser.axe import parse_line

        assert parse_line("not-json") is None

    def test_empty_line_returns_none(self) -> None:
        from parser.axe import parse_line

        assert parse_line("") is None

    def test_iter_events_filters_invalid(self) -> None:
        from parser.axe import iter_events

        lines = [
            '{"run_id":"r","rule_id":"a","impact":"critical","html_snippet":"<x>","dom_path":"x","help_url":"http://h","target_url":"http://t"}',
            "not-json",
            '{"run_id":"r","rule_id":"b","impact":"minor","html_snippet":"<y>","dom_path":"y","help_url":"http://h2","target_url":"http://t2"}',
        ]
        events = list(iter_events(iter(lines)))
        assert len(events) == 2
        assert events[0].metric == "violation.critical"
        assert events[1].metric == "violation.minor"


# ---------------------------------------------------------------------------
# Migration smoke test — verify migration script is importable and has correct chain
# ---------------------------------------------------------------------------


def _load_migration_0005():
    """Load migration module directly from file to avoid local alembic/ shadowing."""
    import importlib.util
    import pathlib
    import sys
    from unittest.mock import MagicMock

    # The local apps/api/alembic/ package shadows the installed alembic package.
    # Inject a stub for alembic.op before exec so `from alembic import op` resolves.
    alembic_mod = sys.modules.get("alembic")
    if alembic_mod is not None and not hasattr(alembic_mod, "op"):
        alembic_mod.op = MagicMock()  # type: ignore[attr-defined]
    if "alembic.op" not in sys.modules:
        sys.modules["alembic.op"] = MagicMock()

    path = pathlib.Path(__file__).parent.parent / "alembic" / "versions" / "0005_a11y_summary_cols.py"
    spec = importlib.util.spec_from_file_location("migration_0005", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[arg-type]
    return mod


class TestMigration0005:
    def test_revision_chain(self) -> None:
        m = _load_migration_0005()
        assert m.revision == "0005"
        assert m.down_revision == "0004"

    def test_has_upgrade_and_downgrade(self) -> None:
        m = _load_migration_0005()
        assert callable(m.upgrade)
        assert callable(m.downgrade)
