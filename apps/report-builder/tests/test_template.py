"""Tests for the Jinja2 run_report.html template.

Validates that the template compiles correctly and produces valid HTML5
containing the expected run metadata.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

SAMPLE_SUMMARY = {
    "http_reqs": 10_000,
    "http_failed": 50,
    "vus_max": 200,
    "p50_ms": 95,
    "p95_ms": 310,
    "p99_ms": 490,
    "status": "completed",
    "started_at": "2026-05-12T10:00:00Z",
    "finished_at": "2026-05-12T10:15:00Z",
}

SAMPLE_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


@pytest.fixture()
def jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )


def render(env: Environment, **kwargs: object) -> str:
    tpl = env.get_template("run_report.html")
    defaults = dict(
        run_id="run-tpl-test-001",
        org_id="org-demo",
        summary=SAMPLE_SUMMARY,
        ai_summary="This is the AI analysis paragraph for the test.",
        chart_latency=SAMPLE_B64,
        chart_error=SAMPLE_B64,
        chart_vus=SAMPLE_B64,
    )
    defaults.update(kwargs)
    return tpl.render(**defaults)


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_template_compiles(jinja_env: Environment):
    """Template can be loaded from filesystem without parse errors."""
    tpl = jinja_env.get_template("run_report.html")
    assert tpl is not None


def test_render_produces_nonempty_html(jinja_env: Environment):
    html = render(jinja_env)
    assert len(html) > 500


def test_html5_doctype(jinja_env: Environment):
    html = render(jinja_env)
    assert html.strip().startswith("<!DOCTYPE html>")


def test_charset_utf8(jinja_env: Environment):
    html = render(jinja_env)
    assert 'charset="UTF-8"' in html or "charset=UTF-8" in html


def test_title_contains_run_id(jinja_env: Environment):
    html = render(jinja_env, run_id="run-unique-9999")
    assert "run-unique-9999" in html


# ---------------------------------------------------------------------------
# Content tests
# ---------------------------------------------------------------------------


def test_org_id_present(jinja_env: Environment):
    html = render(jinja_env, org_id="org-acme")
    assert "org-acme" in html


def test_run_id_in_header_meta(jinja_env: Environment):
    html = render(jinja_env, run_id="run-header-check")
    assert html.count("run-header-check") >= 2  # title + header-meta + footer strip


def test_ai_summary_present(jinja_env: Environment):
    html = render(jinja_env, ai_summary="Bottleneck at /api/checkout endpoint.")
    assert "Bottleneck at /api/checkout endpoint." in html


def test_metric_values_rendered(jinja_env: Environment):
    html = render(jinja_env)
    assert "10000" in html or "10,000" in html or str(SAMPLE_SUMMARY["http_reqs"]) in html
    assert str(SAMPLE_SUMMARY["vus_max"]) in html


def test_charts_embedded_as_data_uris(jinja_env: Environment):
    html = render(jinja_env)
    assert html.count("data:image/png;base64,") == 3


def test_started_at_shown_when_present(jinja_env: Environment):
    html = render(jinja_env)
    assert "2026-05-12T10:00:00Z" in html


def test_missing_optional_fields_do_not_crash(jinja_env: Environment):
    """Template must render without error when summary is empty."""
    html = render(jinja_env, summary={})
    assert "<!DOCTYPE html>" in html


# ---------------------------------------------------------------------------
# AI summary XSS escaping (autoescape=True)
# ---------------------------------------------------------------------------


def test_ai_summary_is_html_escaped(jinja_env: Environment):
    """Autoescape must prevent script injection in the AI summary."""
    malicious = "<script>alert('xss')</script>"
    html = render(jinja_env, ai_summary=malicious)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# Testlyn brand checks
# ---------------------------------------------------------------------------


def test_brand_color_present(jinja_env: Environment):
    html = render(jinja_env)
    assert "#3730A3" in html


def test_jetbrains_mono_referenced(jinja_env: Environment):
    html = render(jinja_env)
    assert "JetBrains Mono" in html


def test_inter_font_referenced(jinja_env: Environment):
    html = render(jinja_env)
    assert "Inter" in html
