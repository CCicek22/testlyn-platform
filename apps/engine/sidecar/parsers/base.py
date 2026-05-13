"""Base parser protocol and shared data types.

Any metric-emitting tool (k6, Playwright, ZAP, axe-core …) can plug in here
by implementing the `Parser` Protocol and returning `SampleEvent` objects.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class SampleEvent:
    """Normalised single metric observation, emitted by any Parser."""

    # metric identity
    metric: str
    metric_type: str  # 'trend' | 'counter' | 'gauge' | 'rate'

    # observation
    timestamp: datetime
    value: float

    # tag set (raw — bucketing happens in the window aggregator)
    tags: dict[str, str] = field(default_factory=dict)


@runtime_checkable
class Parser(Protocol):
    """Async iterator that yields `SampleEvent` objects from an input stream.

    Implementations must tolerate unknown fields in the source format and
    skip unparseable lines with a structured log warning rather than raising.
    """

    def stream(self) -> AsyncIterator[SampleEvent]:
        """Yield `SampleEvent` objects until the source is exhausted or closed."""
        ...
