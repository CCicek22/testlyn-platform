from __future__ import annotations

import structlog
import structlog.stdlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from testlyn_api.config import get_settings
from testlyn_api.products.a11y.routes import router as a11y_router
from testlyn_api.products.a11y.routes import runs_router as a11y_runs_router
from testlyn_api.products.functional.routes import router as functional_router
from testlyn_api.routers import (
    auth,
    internal,
    orgs,
    projects,
    schedules,
    stream,
    targets,
    test_runs,
    tests,
    webhooks,
)

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

app = FastAPI(
    title="Testlyn API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(tests.router)
app.include_router(test_runs.router)
app.include_router(stream.router)
app.include_router(webhooks.router)
app.include_router(schedules.router)
app.include_router(internal.router)
app.include_router(targets.router)
app.include_router(functional_router)
app.include_router(a11y_router)
app.include_router(a11y_runs_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
