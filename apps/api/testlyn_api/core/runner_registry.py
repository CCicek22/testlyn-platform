from __future__ import annotations

from testlyn_api.core.runner import Runner
from testlyn_api.products.load.k6_runner import K6Runner

RUNNERS: dict[str, Runner] = {
    "load": K6Runner(),
}
