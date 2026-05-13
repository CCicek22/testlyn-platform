"""Tests for the k6 JSONL parser.

Covers:
- Metric definition lines are registered (not yielded as events)
- Point lines produce correct SampleEvent fields
- Unknown object types are silently ignored
- Malformed JSON lines are skipped with no crash
- Parser roundtrip: fixture JSONL → expected event count and field values
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sidecar.parsers.k6 import parse_file


@pytest.mark.asyncio
async def test_fixture_roundtrip(k6_fixture_path: Path) -> None:
    """Parse the canonical fixture and assert expected event count and types."""
    events = await parse_file(str(k6_fixture_path))

    # 4 Metric definition lines → not yielded
    # 12 Point lines → 12 events
    assert len(events) == 12

    # All events have a non-empty metric name
    assert all(e.metric for e in events)

    # All events have timezone-aware timestamps
    assert all(e.timestamp.tzinfo is not None for e in events)


@pytest.mark.asyncio
async def test_metric_type_registration(k6_fixture_path: Path) -> None:
    """Verify Metric definitions set the correct type on subsequent Points."""
    events = await parse_file(str(k6_fixture_path))

    duration_events = [e for e in events if e.metric == "http_req_duration"]
    reqs_events = [e for e in events if e.metric == "http_reqs"]
    failed_events = [e for e in events if e.metric == "http_req_failed"]
    vus_events = [e for e in events if e.metric == "vus"]

    assert all(e.metric_type == "trend" for e in duration_events)
    assert all(e.metric_type == "counter" for e in reqs_events)
    assert all(e.metric_type == "rate" for e in failed_events)
    assert all(e.metric_type == "gauge" for e in vus_events)


@pytest.mark.asyncio
async def test_point_fields(k6_fixture_path: Path) -> None:
    """Check that the first http_req_duration event has correct field values."""
    events = await parse_file(str(k6_fixture_path))
    first = next(e for e in events if e.metric == "http_req_duration")

    assert first.value == pytest.approx(120.0)
    assert first.tags["method"] == "GET"
    assert first.tags["status"] == "200"
    assert first.timestamp == datetime(2026, 5, 12, 14, 23, 0, 100000, tzinfo=UTC)


@pytest.mark.asyncio
async def test_unknown_type_ignored(tmp_path: Path) -> None:
    """Lines with unknown 'type' fields are silently skipped."""
    f = tmp_path / "k6.jsonl"
    f.write_text(
        json.dumps({"type": "Unknown", "data": {}, "metric": "x"})
        + "\n"
        + json.dumps(
            {
                "type": "Point",
                "data": {"time": "2026-05-12T14:23:00.000Z", "value": 1.0, "tags": {}},
                "metric": "http_reqs",
            }
        )
        + "\n"
    )
    events = await parse_file(str(f))
    assert len(events) == 1


@pytest.mark.asyncio
async def test_malformed_json_skipped(tmp_path: Path) -> None:
    """Malformed JSON lines are skipped; subsequent valid lines still parsed."""
    f = tmp_path / "k6.jsonl"
    f.write_text(
        "not-json\n"
        + json.dumps(
            {
                "type": "Point",
                "data": {"time": "2026-05-12T14:23:00.000Z", "value": 50.0, "tags": {}},
                "metric": "http_req_duration",
            }
        )
        + "\n"
    )
    events = await parse_file(str(f))
    assert len(events) == 1
    assert events[0].value == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_missing_value_skipped(tmp_path: Path) -> None:
    """Points missing the 'value' field are skipped gracefully."""
    f = tmp_path / "k6.jsonl"
    f.write_text(
        json.dumps(
            {
                "type": "Point",
                "data": {"time": "2026-05-12T14:23:00.000Z", "tags": {}},
                "metric": "http_req_duration",
            }
        )
        + "\n"
    )
    events = await parse_file(str(f))
    assert len(events) == 0


@pytest.mark.asyncio
async def test_extra_fields_tolerated(tmp_path: Path) -> None:
    """Unknown fields in data dict don't cause a crash."""
    f = tmp_path / "k6.jsonl"
    f.write_text(
        json.dumps(
            {
                "type": "Point",
                "data": {
                    "time": "2026-05-12T14:23:00.000Z",
                    "value": 99.0,
                    "tags": {"method": "POST"},
                    "future_field": "ignored",
                },
                "metric": "http_req_duration",
                "another_future_top_field": True,
            }
        )
        + "\n"
    )
    events = await parse_file(str(f))
    assert len(events) == 1
    assert events[0].tags["method"] == "POST"
