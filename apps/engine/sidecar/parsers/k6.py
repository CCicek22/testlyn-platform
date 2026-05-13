"""k6 JSONL parser.

Handles both object types emitted by k6 `--out json`:
  - "Metric"  — one per metric, emitted once at start, carries type metadata
  - "Point"   — one per sample, emitted continuously during the run

Reference: https://grafana.com/docs/k6/latest/results-output/real-time/json/
Pinned against k6 1.3.0 output format. Re-verify on tag bump (spec §4).

Unknown top-level fields are tolerated (dataclass with __slots__ ignores extras
from the raw dict; only mapped keys are used).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import aiofiles
import structlog

from sidecar.parsers.base import SampleEvent

log = structlog.get_logger(__name__)

# k6 metric type strings → our canonical names
_METRIC_TYPE_MAP: dict[str, str] = {
    "trend": "trend",
    "counter": "counter",
    "gauge": "gauge",
    "rate": "rate",
}

# Default type when we see a Point before the corresponding Metric definition
_DEFAULT_METRIC_TYPE = "trend"


class K6Parser:
    """Parses k6 JSONL output from a file or named pipe.

    Usage:
        parser = K6Parser("/tmp/k6.jsonl")
        async for event in parser.stream():
            ...
    """

    def __init__(self, path: str) -> None:
        self._path = path
        # metric_name → metric_type (populated from Metric definition lines)
        self._metric_types: dict[str, str] = {}

    async def stream(self) -> AsyncIterator[SampleEvent]:
        """Open the path (blocking until available) and yield SampleEvents."""
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
            log.warning("k6_parser.invalid_json", line=line[:200])
            return None

        obj_type = obj.get("type")

        if obj_type == "Metric":
            self._handle_metric_def(obj)
            return None

        if obj_type == "Point":
            return self._handle_point(obj)

        # Ignore any other top-level types silently (forward compat)
        return None

    def _handle_metric_def(self, obj: dict) -> None:  # type: ignore[type-arg]
        """Register a metric type so Points can be properly typed."""
        data = obj.get("data", {})
        name: str = obj.get("metric", "") or data.get("name", "")
        raw_type: str = data.get("type", "")
        if name:
            self._metric_types[name] = _METRIC_TYPE_MAP.get(
                raw_type, raw_type or _DEFAULT_METRIC_TYPE
            )

    def _handle_point(self, obj: dict) -> SampleEvent | None:  # type: ignore[type-arg]
        """Convert a k6 Point object to a SampleEvent."""
        metric_name: str = obj.get("metric", "")
        data = obj.get("data", {})

        if not metric_name or not data:
            log.warning("k6_parser.malformed_point", obj=str(obj)[:200])
            return None

        # Timestamp: k6 emits RFC3339 with sub-second precision
        raw_time: str = data.get("time", "")
        try:
            ts = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            log.warning("k6_parser.bad_timestamp", metric=metric_name, time=raw_time)
            return None

        # Ensure timezone-aware UTC
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        value = data.get("value")
        if value is None:
            log.warning("k6_parser.missing_value", metric=metric_name)
            return None

        tags: dict[str, str] = {k: str(v) for k, v in (data.get("tags") or {}).items()}

        metric_type = self._metric_types.get(metric_name, _DEFAULT_METRIC_TYPE)

        return SampleEvent(
            metric=metric_name,
            metric_type=metric_type,
            timestamp=ts,
            value=float(value),
            tags=tags,
        )


async def parse_file(path: str) -> list[SampleEvent]:
    """Helper: parse an entire JSONL file into a list. Used in tests."""
    parser = K6Parser(path)
    return [ev async for ev in parser.stream()]
