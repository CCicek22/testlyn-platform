"""Playwright JSON reporter parser plugin for testlyn-engine-sidecar.

Converts Playwright's `--reporter=json` output to `SampleEvent` objects.

Playwright JSON output shape (top-level):
{
  "suites": [...],
  "stats": { "expected": int, "unexpected": int, "duration": float, ... }
}

Each spec produces entries under suites[*].specs[*].tests[*].results[*].

Sub-metric kinds emitted:
  - test.passed       (counter, value=1 per passed test)
  - test.failed       (counter, value=1 per failed test)
  - test.healed       (counter, value=1 when status=="healed" via tag)
  - test.duration_ms  (trend, value=result.duration in ms)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import aiofiles
import structlog
from sidecar.parsers.base import SampleEvent

log = structlog.get_logger(__name__)


class PlaywrightParser:
    """Parses Playwright JSON reporter output from a file or named pipe.

    Usage:
        parser = PlaywrightParser("/tmp/pw.jsonl")
        async for event in parser.stream():
            ...
    """

    def __init__(self, path: str) -> None:
        self._path = path

    async def stream(self) -> AsyncIterator[SampleEvent]:
        """Read the JSON reporter file and yield SampleEvents."""
        try:
            async with aiofiles.open(self._path) as fh:
                raw = await fh.read()
        except OSError as exc:
            log.warning("playwright_parser.open_error", path=self._path, error=str(exc))
            return

        try:
            report: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("playwright_parser.json_error", error=str(exc))
            return

        now = datetime.now(tz=UTC)

        for suite in report.get("suites", []):
            async for event in self._parse_suite(suite, now):
                yield event

    async def _parse_suite(
        self,
        suite: dict[str, Any],
        default_ts: datetime,
    ) -> AsyncIterator[SampleEvent]:
        for spec in suite.get("specs", []):
            title = spec.get("title", "unknown")
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    async for event in self._parse_result(result, title, default_ts):
                        yield event

        # Recurse into nested suites
        for child in suite.get("suites", []):
            async for event in self._parse_suite(child, default_ts):
                yield event

    async def _parse_result(
        self,
        result: dict[str, Any],
        title: str,
        default_ts: datetime,
    ) -> AsyncIterator[SampleEvent]:
        status: str = result.get("status", "unknown")
        duration_ms: float = float(result.get("duration", 0))
        tags: dict[str, str] = {"title": title, "status": status}

        ts = default_ts

        # Emit duration
        yield SampleEvent(
            metric="test.duration_ms",
            metric_type="trend",
            timestamp=ts,
            value=duration_ms,
            tags=tags,
        )

        # Emit pass/fail counter
        if status == "passed":
            yield SampleEvent(
                metric="test.passed",
                metric_type="counter",
                timestamp=ts,
                value=1.0,
                tags=tags,
            )
        elif status in {"failed", "timedOut", "interrupted"}:
            yield SampleEvent(
                metric="test.failed",
                metric_type="counter",
                timestamp=ts,
                value=1.0,
                tags=tags,
            )

        # healed is signalled by a custom annotation tag in the result
        annotations: list[dict] = result.get("annotations", [])
        if any(a.get("type") == "healed" for a in annotations):
            yield SampleEvent(
                metric="test.healed",
                metric_type="counter",
                timestamp=ts,
                value=1.0,
                tags=tags,
            )
