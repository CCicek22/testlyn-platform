"""Playwright JSONL parser.

Consumes Playwright's `--reporter=json` blob (a single JSON object containing
a `suites` tree with one `tests[].results[]` entry per test attempt).

For Phase-2-stub purposes we emit one `SampleEvent` per test result:

  * `metric`      — `playwright.test`
  * `metric_type` — `counter`
  * `value`       — 1.0 (one test result)
  * `tags`        — `{status, project, file}` plus `title` extra

The aggregator windows these as counter deltas per (status, project, file)
bucket, which is the shape the API queries for pass/fail trend lines.

NB: Playwright emits the whole JSON blob at end-of-run, NOT line-delimited
JSONL.  We therefore read the entire file once and walk the tree, rather
than line-streaming.  Engine entrypoints feed the file into a named pipe
after Playwright exits (see apps/engine-playwright/entrypoint.sh fix #3).
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

_METRIC = "playwright.test"


class PlaywrightParser:
    """Parses Playwright JSON-reporter output from a file or pipe."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def stream(self) -> AsyncIterator[SampleEvent]:
        async with aiofiles.open(self._path) as fh:
            raw = await fh.read()
        if not raw.strip():
            return
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError as exc:
            log.warning("playwright_parser.invalid_json", error=str(exc))
            return

        for event in self._walk(blob):
            yield event

    def _walk(self, blob: dict[str, Any]) -> list[SampleEvent]:
        events: list[SampleEvent] = []
        suites = blob.get("suites") or []
        for suite in suites:
            self._walk_suite(suite, events, file_hint=suite.get("file", ""))
        return events

    def _walk_suite(
        self,
        suite: dict[str, Any],
        out: list[SampleEvent],
        *,
        file_hint: str,
    ) -> None:
        # Playwright suites can nest; recurse before harvesting tests.
        for nested in suite.get("suites") or []:
            self._walk_suite(nested, out, file_hint=nested.get("file") or file_hint)

        for spec in suite.get("specs") or []:
            title = str(spec.get("title") or "")
            for test in spec.get("tests") or []:
                project = str(test.get("projectName") or "")
                for result in test.get("results") or []:
                    status = str(result.get("status") or "unknown")
                    ts = datetime.now(tz=UTC)
                    tags: dict[str, str] = {
                        "status": status,
                        "project": project,
                        "file": file_hint,
                    }
                    if title:
                        tags["title"] = title
                    out.append(
                        SampleEvent(
                            metric=_METRIC,
                            metric_type="counter",
                            timestamp=ts,
                            value=1.0,
                            tags=tags,
                        )
                    )
