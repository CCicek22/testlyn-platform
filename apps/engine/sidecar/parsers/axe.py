"""axe-core JSONL parser.

Consumes the JSONL stream emitted by `apps/engine-a11y/scripts/run-axe.js`.
Each input line is a single violation node with shape:

    {
      "run_id": "...",
      "rule_id": "color-contrast",
      "impact": "serious",          # 'minor' | 'moderate' | 'serious' | 'critical'
      "html_snippet": "<button ...>",
      "dom_path": "html > body > main > button",
      "help_url": "https://dequeuniversity.com/...",
      "target_url": "https://example.com/page"
    }

We emit one `SampleEvent` per violation node, shaped to fit the shared
`samples_1s` schema:

  * `metric`        — `a11y.violation` (stable name for product='a11y' rows)
  * `metric_type`   — `counter` (count of violations per window)
  * `value`         — 1.0 (each line is one violation)
  * `tags`          — `{rule_id, impact, target_url}` plus a `dom_path` extra

This is a Phase-2-stub: it satisfies the dispatch contract from §1 of the
audit so the sidecar can swap parsers on PRODUCT=a11y.  Field semantics may
shift when the a11y product spec is finalised.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiofiles
import structlog

from sidecar.parsers.base import SampleEvent

log = structlog.get_logger(__name__)

_METRIC = "a11y.violation"


class AxeParser:
    """Parses axe-core JSONL output from a file or pipe."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def stream(self) -> AsyncIterator[SampleEvent]:
        async with aiofiles.open(self._path) as fh:
            async for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                event = self._parse_line(line)
                if event is not None:
                    yield event

    def _parse_line(self, line: str) -> SampleEvent | None:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            log.warning("axe_parser.invalid_json", line=line[:200])
            return None

        rule_id = obj.get("rule_id")
        if not rule_id:
            log.warning("axe_parser.missing_rule_id", obj=str(obj)[:200])
            return None

        # axe emits events at wall-clock; sidecar windows it by arrival time.
        ts = datetime.now(tz=UTC)
        tags: dict[str, str] = {
            "rule_id": str(rule_id),
            "impact": str(obj.get("impact") or "unknown"),
            "target_url": str(obj.get("target_url") or ""),
        }
        # dom_path is high-cardinality — stays in tag_extra, not the bucket.
        dom_path = obj.get("dom_path")
        if dom_path:
            tags["dom_path"] = str(dom_path)

        return SampleEvent(
            metric=_METRIC,
            metric_type="counter",
            timestamp=ts,
            value=1.0,
            tags=tags,
        )
