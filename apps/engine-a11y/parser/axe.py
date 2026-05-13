from __future__ import annotations

"""
parser/axe.py — axe-core JSONL → SampleEvent converter for the BQ sidecar.

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
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterator


@dataclass
class SampleEvent:
    """
    Mirrors the sidecar SampleEvent contract.

    Fields align with the samples_1s BigQuery table schema.
    Not all fields are relevant for a11y — nullable ones default to None.
    """

    run_id: str
    org_id: str
    product: str  # always 'a11y'
    region: str
    window_start: datetime
    metric: str  # e.g. 'violation.critical'
    metric_type: str  # always 'counter' for violation counts
    tag_method: str | None = None
    tag_status: str | None = None
    tag_scenario: str | None = None
    tag_group: str | None = None
    tag_name: str | None = None  # target URL
    tag_extra: dict = field(default_factory=dict)
    count: int = 1
    sum_value: float = 1.0
    min_value: float = 1.0
    max_value: float = 1.0
    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    delta: float | None = None
    rate_per_sec: float | None = None
    inserted_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


_VALID_IMPACTS = frozenset(["critical", "serious", "moderate", "minor"])


def parse_line(
    line: str,
    *,
    org_id: str,
    region: str,
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
        run_id=run_id,
        org_id=org_id,
        product="a11y",
        region=region,
        window_start=ts,
        metric=f"violation.{impact}",
        metric_type="counter",
        tag_name=row.get("target_url"),
        tag_extra={
            "rule_id": row.get("rule_id", ""),
            "dom_path": row.get("dom_path", ""),
            "help_url": row.get("help_url", ""),
        },
        count=1,
        sum_value=1.0,
        min_value=1.0,
        max_value=1.0,
        inserted_at=datetime.now(tz=UTC),
    )


def iter_events(
    lines: Iterator[str],
    *,
    org_id: str,
    region: str,
    window_start: datetime | None = None,
) -> Iterator[SampleEvent]:
    """Yield SampleEvents from a JSONL line iterator."""
    for line in lines:
        event = parse_line(line, org_id=org_id, region=region, window_start=window_start)
        if event is not None:
            yield event


if __name__ == "__main__":
    # Allow direct invocation for smoke-testing:
    #   node scripts/run-axe.js | python parser/axe.py
    # Prints parsed event dicts to stderr for inspection.
    org_id = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    region = sys.argv[2] if len(sys.argv) > 2 else "us-central1"
    for event in iter_events(sys.stdin, org_id=org_id, region=region):
        print(json.dumps(event.__dict__, default=str), file=sys.stderr)
