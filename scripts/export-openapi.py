#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to docs/api/openapi-v1.yaml.

Usage:
    python scripts/export-openapi.py

Environment:
    TESTING=1 is set automatically so application startup skips side-effects
    (Cloud Tasks client init, Redis connect, etc.).

Idempotent — safe to run on every commit in CI.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Must be set before any app imports so config guards skip side-effectful init.
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DEV_AUTH_BYPASS", "true")
os.environ.setdefault("RUN_MODE", "docker")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("GCP_PROJECT_ID", "example-project-prod")
os.environ.setdefault("GCP_REGION", "us-central1")
os.environ.setdefault("GCS_SCRIPTS_BUCKET", "testlyn-prod-scripts")
os.environ.setdefault("GCS_RESULTS_BUCKET", "testlyn-prod-results")
os.environ.setdefault("GCS_REPORTS_BUCKET", "testlyn-prod-reports")
os.environ.setdefault("GCP_BQ_DATASET", "testlyn_metrics")
os.environ.setdefault("CLOUD_TASKS_QUEUE", "testlyn-run-queue")
os.environ.setdefault("API_BASE_URL", "https://api.testlyn.io")
os.environ.setdefault("FIREBASE_PROJECT_ID", "example-project-prod")
os.environ.setdefault("WEB_BASE_URL", "https://testlyn.io")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_PLACEHOLDER")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_PLACEHOLDER")

# Ensure apps/api is on sys.path when running from repo root
REPO_ROOT = Path(__file__).parent.parent
API_SRC = REPO_ROOT / "apps" / "api"
if str(API_SRC) not in sys.path:
    sys.path.insert(0, str(API_SRC))

import yaml  # pyyaml

# --------------------------------------------------------------------------- #
# Import the app — guard against known transient router registration errors    #
# --------------------------------------------------------------------------- #
try:
    from testlyn_api.main import app
    _import_error: str | None = None
except Exception as exc:
    # Some routers may fail to register if a dependency signature is invalid
    # (e.g. bare AsyncSession param without Depends wrapper — a known W3A bug).
    # Build a minimal app from the subset of routers that do load cleanly.
    print(f"WARNING: main.py import failed ({exc}). Building partial spec.", flush=True)
    _import_error = str(exc)

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Testlyn API",
        version="0.1.0",
    )

    _SAFE_ROUTERS = [
        ("testlyn_api.routers.auth", "router"),
        ("testlyn_api.routers.orgs", "router"),
        ("testlyn_api.routers.projects", "router"),
        ("testlyn_api.routers.tests", "router"),
        ("testlyn_api.routers.test_runs", "router"),
        ("testlyn_api.routers.stream", "router"),
        ("testlyn_api.routers.webhooks", "router"),
        ("testlyn_api.routers.schedules", "router"),
        ("testlyn_api.routers.targets", "router"),
        ("testlyn_api.routers.internal", "router"),
    ]

    for mod_name, attr in _SAFE_ROUTERS:
        try:
            import importlib
            mod = importlib.import_module(mod_name)
            app.include_router(getattr(mod, attr))
        except Exception as router_exc:
            print(f"  SKIP {mod_name}: {router_exc}", flush=True)

# --------------------------------------------------------------------------- #
# Patch top-level metadata                                                      #
# --------------------------------------------------------------------------- #
schema = app.openapi()
schema["info"]["version"] = "1.0.0"
schema["info"]["contact"] = {
    "name": "Testlyn Support",
    "email": "support@testlyn.io",
    "url": "https://testlyn.io/docs/api/v1",
}
schema["info"]["license"] = {
    "name": "Proprietary",
    "url": "https://testlyn.io/legal/terms",
}
schema["servers"] = [
    {"url": "https://api.testlyn.io/v1", "description": "Production"},
    {"url": "http://localhost:8080/v1", "description": "Local development"},
]

if _import_error:
    schema["info"]["x-export-warning"] = (
        "Partial spec — some routers excluded due to import error. "
        f"Fix root cause: {_import_error}"
    )

# --------------------------------------------------------------------------- #
# Write output                                                                  #
# --------------------------------------------------------------------------- #
out_path = REPO_ROOT / "docs" / "api" / "openapi-v1.yaml"
out_path.parent.mkdir(parents=True, exist_ok=True)

with open(out_path, "w", encoding="utf-8") as fh:
    yaml.dump(schema, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)

op_count = sum(
    1
    for path_item in schema.get("paths", {}).values()
    for method in ("get", "post", "put", "patch", "delete", "head", "options", "trace")
    if method in path_item
)

print(f"Wrote {out_path.relative_to(REPO_ROOT)}  ({op_count} operations)")
if _import_error:
    print("NOTE: Partial spec — fix the W3A auth.py/permissions.py router registration bug for a complete export.")
