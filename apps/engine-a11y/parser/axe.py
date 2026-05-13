"""
parser/axe.py — axe-core JSONL -> SampleEvent converter for the BQ sidecar.

Plugs into the same sidecar pipeline used by the load engine parser.
Each JSONL line from run-axe.js becomes one SampleEvent row in BQ
with product='a11y'.

Submetric kinds:
  violation.critical
  violation.serious
  violation.moderate
  violation.minor

Each kind maps to a single count=1 SampleEvent so the BQ aggregation query
can sum violations by impact level over a run_id.

See: docs/testlyn_bq_sidecar_spec.md §4 for the SampleEvent schema.

Tags (per R1 review spec):
  severity   -- critical | serious | moderate | minor
  rule_id    -- axe rule identifier
  target_url -- page URL where the violation was found
  dom_path   -- CSS selector path of the offending element
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

from sidecar.parsers.base import SampleEvent

_VALID_IMPACTS = frozenset(["critical", "serious", "moderate", "minor"])


def parse_line(
    line: str,
    *,
    window_start: datetime | None = None,
) -> SampleEvent | None:
    """
    Parse one JSONL line from run-axe.js into a SampleEvent.

    Returns None if the line is malformed or has an unrecognised impact.
    """
    line = line.strip()
    if not line:
        return None

    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None

    impact = row.get("impact", "")
    if impact not in _VALID_IMPACTS:
        return None

    run_id = row.get("run_id", "")
    if not run_id:
        return None

    ts = window_start or datetime.now(tz=UTC)

    return SampleEvent(
        metric=f"violation.{impact}",
        metric_type="counter",
        timestamp=ts,
        value=1.0,
        tags={
            "severity": impact,
            "rule_id": row.get("rule_id", ""),
            "target_url": row.get("target_url", ""),
            "dom_path": row.get("dom_path", ""),
        },
    )


def iter_events(
    lines: Iterator[str],
    *,
    window_start: datetime | None = None,
) -> Iterator[SampleEvent]:
    """Yield SampleEvents from a JSONL line iterator."""
    for line in lines:
        event = parse_line(line, window_start=window_start)
        if event is not None:
            yield event


if __name__ == "__main__":
    # Allow direct invocation for smoke-testing:
    #   node scripts/run-axe.js | python parser/axe.py
    # Prints parsed event dicts to stderr for inspection.
    for event in iter_events(sys.stdin):
        print(
            json.dumps(
                {
                    "metric": event.metric,
                    "metric_type": event.metric_type,
                    "timestamp": event.timestamp.isoformat(),
                    "value": event.value,
                    "tags": event.tags,
                },
                default=str,
            ),
            file=sys.stderr,
        )
