"""Tests for the parser dispatch (k6 / axe / playwright) and config INPUT_PATH."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sidecar.config import SidecarConfig
from sidecar.main import _build_parser
from sidecar.parsers.axe import AxeParser
from sidecar.parsers.k6 import K6Parser
from sidecar.parsers.playwright import PlaywrightParser


def _cfg(**overrides) -> SidecarConfig:  # type: ignore[no-untyped-def]
    base = {
        "RUN_ID": "r1",
        "ORG_ID": "o1",
        "GCP_PROJECT": "proj",
    }
    base.update(overrides)
    return SidecarConfig(**base)


class TestDispatch:
    def test_default_is_k6(self) -> None:
        assert isinstance(_build_parser(_cfg()), K6Parser)

    def test_axe_dispatch(self) -> None:
        assert isinstance(_build_parser(_cfg(PARSER="axe")), AxeParser)

    def test_playwright_dispatch(self) -> None:
        assert isinstance(_build_parser(_cfg(PARSER="playwright")), PlaywrightParser)

    def test_case_insensitive(self) -> None:
        assert isinstance(_build_parser(_cfg(PARSER="AXE")), AxeParser)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown PARSER"):
            _build_parser(_cfg(PARSER="zap"))


class TestInputPath:
    def test_input_path_falls_back_to_k6_output_path(self) -> None:
        cfg = _cfg(K6_OUTPUT_PATH="/tmp/legacy.jsonl")
        assert cfg.input_path == "/tmp/legacy.jsonl"

    def test_input_path_takes_precedence(self) -> None:
        cfg = _cfg(
            INPUT_PATH="/tmp/new.jsonl",
            K6_OUTPUT_PATH="/tmp/legacy.jsonl",
        )
        assert cfg.input_path == "/tmp/new.jsonl"


class TestAxeParser:
    @pytest.mark.asyncio
    async def test_parses_violation_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "axe.jsonl"
        f.write_text(
            json.dumps(
                {
                    "run_id": "r1",
                    "rule_id": "color-contrast",
                    "impact": "serious",
                    "html_snippet": "<button>x</button>",
                    "dom_path": "html > body > button",
                    "help_url": "https://example.com/help",
                    "target_url": "https://example.com/page",
                }
            )
            + "\n"
        )
        parser = AxeParser(str(f))
        events = [e async for e in parser.stream()]
        assert len(events) == 1
        assert events[0].metric == "a11y.violation"
        assert events[0].metric_type == "counter"
        assert events[0].value == 1.0
        assert events[0].tags["rule_id"] == "color-contrast"
        assert events[0].tags["impact"] == "serious"

    @pytest.mark.asyncio
    async def test_skips_missing_rule_id(self, tmp_path: Path) -> None:
        f = tmp_path / "axe.jsonl"
        f.write_text(json.dumps({"impact": "serious"}) + "\n")
        parser = AxeParser(str(f))
        events = [e async for e in parser.stream()]
        assert events == []


class TestPlaywrightParser:
    @pytest.mark.asyncio
    async def test_walks_suites_specs_results(self, tmp_path: Path) -> None:
        blob = {
            "suites": [
                {
                    "file": "tests/checkout.spec.ts",
                    "specs": [
                        {
                            "title": "checks out",
                            "tests": [
                                {
                                    "projectName": "chromium",
                                    "results": [{"status": "passed"}],
                                }
                            ],
                        },
                        {
                            "title": "fails on bad card",
                            "tests": [
                                {
                                    "projectName": "chromium",
                                    "results": [{"status": "failed"}],
                                }
                            ],
                        },
                    ],
                }
            ]
        }
        f = tmp_path / "pw.json"
        f.write_text(json.dumps(blob))
        parser = PlaywrightParser(str(f))
        events = [e async for e in parser.stream()]
        assert len(events) == 2
        statuses = sorted(e.tags["status"] for e in events)
        assert statuses == ["failed", "passed"]
        assert all(e.metric == "playwright.test" for e in events)
        assert all(e.metric_type == "counter" for e in events)
