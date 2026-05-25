"""Regression test for sidecar logging configuration.

Guards against the startup crash where `structlog.stdlib.add_logger_name`
(which reads `logger.name`) was combined with `PrintLoggerFactory` (whose
PrintLogger has no `.name`), raising AttributeError on the first log call and
killing the sidecar before it could stream any metrics.
"""

from __future__ import annotations

import structlog

from sidecar.main import _configure_logging


def test_configure_logging_does_not_crash_on_first_log() -> None:
    _configure_logging("INFO")
    log = structlog.get_logger("sidecar.main")
    # Must not raise AttributeError: 'PrintLogger' object has no attribute 'name'
    log.info("sidecar.started", run_id="r", org_id="o", product="load")
