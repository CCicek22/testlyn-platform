"""Tests for the tumbling-window aggregator.

Covers:
- Count, min, max correctness
- Percentile accuracy (t-digest ±1% vs numpy reference)
- Window boundary: samples in different seconds produce different windows
- Gauge: last value wins
- Counter: delta accumulates
- Rate: success/total ratio
- flush_all returns all remaining windows
"""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from sidecar.parsers.base import SampleEvent
from sidecar.windows import MAX_LATE_WINDOWS, WindowAggregator, _window_start_for


def _ts(sec: float, subsec: float = 0.0) -> datetime:
    """Build a UTC datetime at a specific second offset from epoch zero."""
    return datetime.fromtimestamp(sec + subsec, tz=UTC)


def _make_aggregator(**kwargs) -> WindowAggregator:  # type: ignore[no-untyped-def]
    defaults = dict(run_id="run1", org_id="org1", product="load", region="us-central1")
    defaults.update(kwargs)
    return WindowAggregator(**defaults)  # type: ignore[arg-type]


def _trend_event(ts: datetime, value: float, **tag_kwargs: str) -> SampleEvent:
    tags = {"method": "GET", "status": "200", "scenario": "default", "group": "", "name": "test"}
    tags.update(tag_kwargs)
    return SampleEvent(
        metric="http_req_duration",
        metric_type="trend",
        timestamp=ts,
        value=value,
        tags=tags,
    )


class TestWindowBoundaries:
    def test_same_second_same_window(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0  # fixed epoch second
        closed: list = []
        for sub in [0.1, 0.5, 0.9]:
            closed += agg.add(_trend_event(_ts(base, sub), 100.0))
        assert closed == []  # no window closed yet (no sample from next second)

    def test_next_second_keeps_window_open_within_late_horizon(self) -> None:
        """A window must stay open until it falls MORE than MAX_LATE_WINDOWS
        behind the newest window — closing it on the very next second meant a
        tolerated late sample could re-create (duplicate-emit) it."""
        agg = _make_aggregator()
        base = 1_715_000_000.0
        agg.add(_trend_event(_ts(base, 0.1), 100.0))
        agg.add(_trend_event(_ts(base, 0.2), 200.0))
        closed = agg.add(_trend_event(_ts(base + 1, 0.1), 300.0))
        assert closed == []  # still within the late-sample horizon
        remaining = agg.flush_all()
        assert len(remaining) == 2

    def test_window_closes_beyond_late_horizon(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        agg.add(_trend_event(_ts(base, 0.1), 100.0))
        agg.add(_trend_event(_ts(base, 0.2), 200.0))
        closed = agg.add(_trend_event(_ts(base + MAX_LATE_WINDOWS + 1, 0.1), 300.0))
        assert len(closed) == 1
        w = closed[0]
        assert w.count == 2
        assert w.min_value == pytest.approx(100.0)
        assert w.max_value == pytest.approx(200.0)
        assert w.sum_value == pytest.approx(300.0)

    def test_each_window_emitted_exactly_once_with_late_samples(self) -> None:
        """Regression for the duplicate-emission bug: a tolerated late sample
        (within MAX_LATE_WINDOWS) must never target a window that has already
        been emitted."""
        agg = _make_aggregator()
        base = 1_715_000_000.0
        emitted: list = []

        emitted += agg.add(_trend_event(_ts(base, 0.1), 100.0))
        # Jump ahead: closes the base window (it is now > horizon behind).
        emitted += agg.add(_trend_event(_ts(base + MAX_LATE_WINDOWS + 1, 0.1), 1.0))
        assert len(emitted) == 1

        # Late-but-tolerated sample (within the horizon of the newest window).
        # Its window was never emitted, so no duplicate is possible.
        emitted += agg.add(_trend_event(_ts(base + 2, 0.1), 50.0))
        emitted += agg.flush_all()

        starts = [w.window_start.isoformat() for w in emitted]
        assert len(starts) == len(set(starts)), f"duplicate window emission: {starts}"
        assert len(emitted) == 3  # base, base+2, base+horizon+1

    def test_too_late_sample_is_dropped(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        agg.add(_trend_event(_ts(base + MAX_LATE_WINDOWS + 1, 0.1), 1.0))
        # Older than (latest - MAX_LATE_WINDOWS) → dropped, no window created.
        closed = agg.add(_trend_event(_ts(base, 0.1), 100.0))
        assert closed == []
        remaining = agg.flush_all()
        assert len(remaining) == 1  # only the newest window exists

    def test_flush_all_returns_remaining(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        agg.add(_trend_event(_ts(base, 0.1), 100.0))
        agg.add(_trend_event(_ts(base, 0.5), 150.0))
        remaining = agg.flush_all()
        assert len(remaining) == 1
        assert remaining[0].count == 2


class TestPercentileAccuracy:
    """t-digest percentiles must be within ±2% of numpy reference."""

    def test_uniform_distribution(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        rng = np.random.default_rng(42)
        values = rng.uniform(0, 1000, size=1000).tolist()

        for i, v in enumerate(values):
            agg.add(_trend_event(_ts(base, i * 0.0001), v))

        # Trigger close by adding a sample in the next second
        closed = agg.add(_trend_event(_ts(base + 1, 0.0), 0.0))
        closed += agg.flush_all()

        # Find the window with 1000 samples
        big_w = max(closed, key=lambda w: w.count)

        np_arr = np.array(values)
        for attr, p in [("p50", 50), ("p90", 90), ("p95", 95), ("p99", 99)]:
            actual = getattr(big_w, attr)
            expected = float(np.percentile(np_arr, p))
            if expected != 0:
                rel_err = abs(actual - expected) / expected
                assert rel_err < 0.02, (
                    f"p{p}: got {actual:.3f}, expected {expected:.3f}, "
                    f"relative error {rel_err:.4f} > 2%"
                )

    def test_known_values_count_min_max(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        known = [10.0, 20.0, 30.0, 40.0, 50.0]
        for i, v in enumerate(known):
            agg.add(_trend_event(_ts(base, i * 0.1), v))
        closed = agg.flush_all()
        assert len(closed) == 1
        w = closed[0]
        assert w.count == 5
        assert w.min_value == pytest.approx(10.0)
        assert w.max_value == pytest.approx(50.0)
        assert w.sum_value == pytest.approx(150.0)


class TestMetricTypes:
    def test_counter_accumulates_delta(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        for _ in range(5):
            agg.add(
                SampleEvent(
                    metric="http_reqs",
                    metric_type="counter",
                    timestamp=_ts(base, 0.1),
                    value=1.0,
                    tags={
                        "method": "GET",
                        "status": "200",
                        "scenario": "default",
                        "group": "",
                        "name": "x",
                    },
                )
            )
        closed = agg.flush_all()
        assert closed[0].delta == pytest.approx(5.0)

    def test_gauge_last_value_wins(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        for v in [5.0, 10.0, 15.0, 8.0]:
            agg.add(
                SampleEvent(
                    metric="vus",
                    metric_type="gauge",
                    timestamp=_ts(base, 0.1),
                    value=v,
                    tags={},
                )
            )
        closed = agg.flush_all()
        assert closed[0].delta == pytest.approx(8.0)

    def test_rate_success_ratio(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        # 3 successes (value=1) + 1 failure (value=0)
        for v in [1.0, 1.0, 0.0, 1.0]:
            agg.add(
                SampleEvent(
                    metric="http_req_failed",
                    metric_type="rate",
                    timestamp=_ts(base, 0.1),
                    value=v,
                    tags={},
                )
            )
        closed = agg.flush_all()
        w = closed[0]
        assert w.rate_per_sec == pytest.approx(3.0)  # 3 successes / 1 second


class TestTagBucketing:
    def test_different_status_produces_different_buckets(self) -> None:
        agg = _make_aggregator()
        base = 1_715_000_000.0
        agg.add(_trend_event(_ts(base, 0.1), 100.0, status="200"))
        agg.add(_trend_event(_ts(base, 0.2), 200.0, status="500"))
        closed = agg.flush_all()
        assert len(closed) == 2  # two distinct tag buckets


class TestWindowStartAlignment:
    @pytest.mark.parametrize(
        "ts_float,expected_start",
        [
            (1_715_000_000.5, 1_715_000_000),
            (1_715_000_000.0, 1_715_000_000),
            (1_715_000_000.999, 1_715_000_000),
            (1_715_000_001.0, 1_715_000_001),
        ],
    )
    def test_alignment(self, ts_float: float, expected_start: int) -> None:
        ts = datetime.fromtimestamp(ts_float, tz=UTC)
        ws = _window_start_for(ts, 1)
        assert int(ws.timestamp()) == expected_start
