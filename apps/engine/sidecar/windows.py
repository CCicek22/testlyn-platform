"""Tumbling-window aggregator for k6 SampleEvents.

Window strategy
---------------
1-second tumbling windows aligned to UTC second boundaries (not test-relative).
One window per (metric_name, tag_bucket_key). On window close we emit a
`WindowSample` with count/sum/min/max/p50/p90/p95/p99.

Percentile algorithm
--------------------
We retain all samples in a `list[float]` per (metric, tag_bucket) bucket for
each open window, then compute exact percentiles with `numpy.percentile` at
window close.

Why numpy over t-digest:
  - `tdigest` 0.5.x depends on `accumulation-tree` (Cython), which requires a
    C compiler at install time.  `python:3.13-slim` ships no `gcc`, so the
    wheel build fails.  Adding `build-essential` bloats the image and couples
    us to a native toolchain.
  - `numpy` ships prebuilt wheels for every CPython/platform combo we target
    (linux/amd64, linux/arm64), installs without a compiler, and is already a
    direct dependency for the stats pipeline.
  - Memory bound: at 200k samples/sec and 1-second windows, worst case is
    ~200k float64 values x 8 bytes = 1.6 MB per (metric, tag_bucket) window.
    In practice the cardinality of live (metric, tag_bucket) combinations for
    a single k6 run is ~50-200 combinations, and each window is flushed every
    second, so peak resident memory for open windows stays well under 100 MB.
  - Accuracy: numpy.percentile uses linear interpolation by default — exact on
    the observed distribution, no approximation error.

Clock-skew tolerance
--------------------
We hold at most MAX_LATE_WINDOWS=5 concurrent windows per (metric, tag_bucket).
When a sample arrives for a window that is >MAX_LATE_WINDOWS seconds before the
newest known window, it is dropped with a warning. Older windows are flushed
when a sample arrives for a strictly newer window.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import structlog

from sidecar.parsers.base import SampleEvent

log = structlog.get_logger(__name__)

# How many concurrent "late" windows we tolerate per (metric, tag_bucket)
MAX_LATE_WINDOWS = 5

# Default tag keys used for bucketing (cardinality-controlled grouping)
_DEFAULT_TAG_KEYS = ("method", "status", "scenario", "group", "name")


@dataclass(slots=True)
class WindowSample:
    """Aggregated result for one (metric, tag_bucket, 1-second window)."""

    run_id: str
    org_id: str
    product: str
    region: str

    window_start: datetime
    metric: str
    metric_type: str

    # Tag bucket (indexed fields)
    tag_method: str | None
    tag_status: str | None
    tag_scenario: str | None
    tag_group: str | None
    tag_name: str | None
    tag_extra: dict[str, str]  # non-indexed tags

    # Trend aggregates
    count: int
    sum_value: float
    min_value: float | None
    max_value: float | None
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None

    # Counter / gauge / rate
    delta: float
    rate_per_sec: float | None

    def to_bq_row(self) -> dict:  # type: ignore[type-arg]
        """Convert to a dict suitable for BigQuery `insert_rows_json`."""
        return {
            "run_id": self.run_id,
            "org_id": self.org_id,
            "product": self.product,
            "region": self.region,
            "window_start": self.window_start.isoformat(),
            "metric": self.metric,
            "metric_type": self.metric_type,
            "tag_method": self.tag_method,
            "tag_status": self.tag_status,
            "tag_scenario": self.tag_scenario,
            "tag_group": self.tag_group,
            "tag_name": self.tag_name,
            "tag_extra": json.dumps(self.tag_extra) if self.tag_extra else None,
            "count": self.count,
            "sum_value": self.sum_value,
            "min_value": self.min_value,
            "max_value": self.max_value,
            "p50": self.p50,
            "p90": self.p90,
            "p95": self.p95,
            "p99": self.p99,
            "delta": self.delta,
            "rate_per_sec": self.rate_per_sec,
        }


class _WindowBucket:
    """Accumulates samples for a single (metric, tag_bucket, window_start) triple."""

    __slots__ = (
        "_count",
        "_delta",
        "_max",
        "_min",
        "_rate_success",
        "_rate_total",
        "_samples",
        "_sum",
        "metric_type",
        "window_start",
    )

    def __init__(self, metric_type: str, window_start: datetime) -> None:
        self.metric_type = metric_type
        self.window_start = window_start
        self._samples: list[float] = []
        self._count = 0
        self._sum = 0.0
        self._min: float | None = None
        self._max: float | None = None
        self._delta = 0.0
        self._rate_success = 0.0
        self._rate_total = 0

    def add(self, value: float) -> None:
        self._count += 1
        self._delta += value

        if self.metric_type == "trend":
            self._sum += value
            self._min = value if self._min is None else min(self._min, value)
            self._max = value if self._max is None else max(self._max, value)
            self._samples.append(value)
        elif self.metric_type == "gauge":
            # latest value wins
            self._delta = value
        elif self.metric_type == "rate":
            self._rate_total += 1
            if value == 1.0:
                self._rate_success += 1.0
        # counter: delta is already the running sum

    def percentile(self, p: float) -> float | None:
        """Return the p-th percentile (0-100) via numpy, or None if no samples."""
        if not self._samples:
            return None
        return float(np.percentile(self._samples, p))

    def close(self, window_seconds: float = 1.0) -> dict:  # type: ignore[type-arg]
        """Return the aggregated stats dict (used to build WindowSample)."""
        # rate_per_sec semantics (spec §6): for 'rate' metrics, emit the count of
        # successful observations per second in this window (successes / window_s).
        # This is NOT a dimensionless fraction (0-1); it is an absolute rate in
        # units of [events/second].  BQ consumers that want a success fraction
        # should compute (rate_per_sec * window_s) / count themselves.
        # Decision recorded here to prevent future drift. — R1-C1 2026-05-13
        rate: float | None = None
        if self.metric_type == "rate" and self._rate_total > 0:
            rate = self._rate_success / window_seconds

        p50 = p90 = p95 = p99 = None
        if self.metric_type == "trend" and self._count > 0:
            p50 = self.percentile(50)
            p90 = self.percentile(90)
            p95 = self.percentile(95)
            p99 = self.percentile(99)

        return {
            "count": self._count,
            "sum_value": self._sum,
            "min_value": self._min,
            "max_value": self._max,
            "p50": p50,
            "p90": p90,
            "p95": p95,
            "p99": p99,
            "delta": self._delta,
            "rate_per_sec": rate,
        }


def _bucket_key(tags: dict[str, str], tag_keys: tuple[str, ...]) -> tuple[str, ...]:
    """Extract the indexed tag values (in order) for bucketing."""
    return tuple(tags.get(k, "") for k in tag_keys)


def _tag_extra(tags: dict[str, str], indexed_keys: tuple[str, ...]) -> dict[str, str]:
    """Return tags that are NOT in the indexed key set."""
    return {k: v for k, v in tags.items() if k not in indexed_keys}


def _window_start_for(ts: datetime, window_seconds: int) -> datetime:
    """Align a timestamp to the UTC second boundary of its window."""
    epoch = ts.timestamp()
    aligned = (int(epoch) // window_seconds) * window_seconds
    return datetime.fromtimestamp(aligned, tz=UTC)


class WindowAggregator:
    """Tumbling-window aggregator.

    Not thread-safe — designed for a single asyncio event loop.
    """

    def __init__(
        self,
        *,
        run_id: str,
        org_id: str,
        product: str,
        region: str,
        window_seconds: int = 1,
        tag_keys: tuple[str, ...] = _DEFAULT_TAG_KEYS,
    ) -> None:
        self._run_id = run_id
        self._org_id = org_id
        self._product = product
        self._region = region
        self._window_seconds = window_seconds
        self._tag_keys = tag_keys

        # (metric_name, bucket_key_tuple) → {window_start_iso → _WindowBucket}
        self._windows: dict[tuple[str, tuple[str, ...]], dict[str, _WindowBucket]] = {}

        # Track most-recent window start per (metric, bucket) for late-arrival detection
        self._latest_window: dict[tuple[str, tuple[str, ...]], datetime] = {}

    def add(self, event: SampleEvent) -> list[WindowSample]:
        """Add a sample; return any windows that are now closed and should be emitted."""
        bucket_vals = _bucket_key(event.tags, self._tag_keys)
        key = (event.metric, bucket_vals)
        ws = _window_start_for(event.timestamp, self._window_seconds)

        # Update "latest window" tracker
        latest = self._latest_window.get(key)
        if latest is None or ws > latest:
            self._latest_window[key] = ws

        # Drop late samples that are too old
        cutoff = self._latest_window[key] - timedelta(
            seconds=self._window_seconds * MAX_LATE_WINDOWS
        )
        if ws < cutoff:
            log.warning(
                "windows.late_sample_dropped",
                metric=event.metric,
                window_start=ws.isoformat(),
                cutoff=cutoff.isoformat(),
            )
            return []

        # Flush windows older than the current one for this key
        closed: list[WindowSample] = []
        if key in self._windows:
            for existing_ws_iso in list(self._windows[key].keys()):
                existing_ws = datetime.fromisoformat(existing_ws_iso)
                if existing_ws < ws:
                    closed.append(self._close_window(key, existing_ws_iso, event))

        # Accumulate into the target window
        windows_for_key = self._windows.setdefault(key, {})
        ws_iso = ws.isoformat()
        if ws_iso not in windows_for_key:
            windows_for_key[ws_iso] = _WindowBucket(event.metric_type, ws)
        windows_for_key[ws_iso].add(event.value)

        return closed

    def flush_all(self) -> list[WindowSample]:
        """Close and return all remaining open windows. Call after k6 EOF."""
        closed: list[WindowSample] = []
        for key in list(self._windows.keys()):
            for ws_iso in list(self._windows.get(key, {}).keys()):
                closed.append(self._close_window(key, ws_iso, None))
        return closed

    def _close_window(
        self,
        key: tuple[str, tuple[str, ...]],
        ws_iso: str,
        trigger_event: SampleEvent | None,
    ) -> WindowSample:
        metric_name, bucket_vals = key
        bucket: _WindowBucket = self._windows[key].pop(ws_iso)
        if not self._windows[key]:
            del self._windows[key]

        stats = bucket.close(window_seconds=float(self._window_seconds))

        # Reconstruct tags from bucket key
        indexed: dict[str, str] = dict(zip(self._tag_keys, bucket_vals, strict=False))
        extra = {}
        if trigger_event:
            extra = _tag_extra(trigger_event.tags, self._tag_keys)

        log.debug(
            "windows.window_emitted",
            metric=metric_name,
            window_start=ws_iso,
            count=stats["count"],
        )

        return WindowSample(
            run_id=self._run_id,
            org_id=self._org_id,
            product=self._product,
            region=self._region,
            window_start=bucket.window_start,
            metric=metric_name,
            metric_type=bucket.metric_type,
            tag_method=indexed.get("method") or None,
            tag_status=indexed.get("status") or None,
            tag_scenario=indexed.get("scenario") or None,
            tag_group=indexed.get("group") or None,
            tag_name=indexed.get("name") or None,
            tag_extra=extra,
            **stats,
        )
