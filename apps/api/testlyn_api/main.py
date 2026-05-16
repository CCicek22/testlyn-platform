from __future__ import annotations

import structlog
import structlog.stdlib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from testlyn_api.config import get_settings
from testlyn_api.core.firebase import init_firebase
from testlyn_api.core.ip_allowlist import IPAllowlistMiddleware
from testlyn_api.core.rate_limit import RateLimitMiddleware
from testlyn_api.products.a11y.routes import router as a11y_router
from testlyn_api.products.a11y.routes import runs_router as a11y_runs_router
from testlyn_api.products.api_contract.routes import router as api_contract_router
from testlyn_api.products.cicd_insights.routes import router as cicd_insights_router
from testlyn_api.products.eng_analytics.routes import router as eng_analytics_router
from testlyn_api.products.functional.routes import router as functional_router
from testlyn_api.products.mobile.routes import router as mobile_router
from testlyn_api.products.qa_maturity.routes import router as qa_maturity_router
from testlyn_api.products.rum.routes import router as rum_router
from testlyn_api.products.security.routes import router as security_router
from testlyn_api.products.synthetic_data.routes import router as synthetic_data_router
from testlyn_api.products.tdm.routes import router as tdm_router
from testlyn_api.products.visual.routes import router as visual_router
from testlyn_api.routers import (
    audit,
    auth,
    enterprise,
    insights,
    internal,
    orgs,
    projects,
    schedules,
    scim,
    sso,
    stream,
    targets,
    test_runs,
    tests,
    webhooks,
    webhooks_admin,
)
from testlyn_api.routers.graphql import graphql_router

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
init_firebase()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_base_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Rate limiting for /v1/ routes — must be added after CORS so CORS headers are
# present even on 429 responses.  The middleware self-filters to /v1/ paths.
app.add_middleware(RateLimitMiddleware)
# IP allowlist enforcement — rejects /v1/ requests from IPs outside the org's
# configured CIDRs.  Off by default (no entries = allow-all).
app.add_middleware(IPAllowlistMiddleware)

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
app.include_router(webhooks_admin.router)
app.include_router(audit.router)
app.include_router(synthetic_data_router)
app.include_router(api_contract_router)
app.include_router(security_router)
app.include_router(insights.router)
app.include_router(mobile_router)
app.include_router(visual_router)
app.include_router(rum_router)
app.include_router(tdm_router)
app.include_router(qa_maturity_router)
app.include_router(eng_analytics_router)
app.include_router(cicd_insights_router)
app.include_router(sso.router)
app.include_router(scim.router)
app.include_router(enterprise.router)
app.include_router(graphql_router)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
