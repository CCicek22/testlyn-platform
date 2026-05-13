"""Minimal health/readiness HTTP server on port 8081.

Endpoints:
  GET /healthz  — always 200 if the sidecar process is alive
  GET /readyz   — 200 once the sidecar has started processing (i.e. connected
                  to the k6 output pipe); 503 until then

Used by Cloud Run liveness + readiness probes.
"""

from __future__ import annotations

import structlog
from aiohttp import web

log = structlog.get_logger(__name__)


class HealthServer:
    def __init__(self, port: int = 8081) -> None:
        self._port = port
        self._ready = False
        self._app = web.Application()
        self._app.router.add_get("/healthz", self._healthz)
        self._app.router.add_get("/readyz", self._readyz)
        self._runner: web.AppRunner | None = None

    def mark_ready(self) -> None:
        self._ready = True

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        log.info("health.server_started", port=self._port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _healthz(self, _request: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def _readyz(self, _request: web.Request) -> web.Response:
        if self._ready:
            return web.Response(text="ready")
        return web.Response(status=503, text="not ready")
