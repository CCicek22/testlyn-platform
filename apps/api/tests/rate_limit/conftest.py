"""Isolated conftest for rate_limit tests.

These tests build their own minimal FastAPI apps and do NOT import
testlyn_api.main (which has a known W3A-introduced router registration bug
that blocks the shared conftest from loading).

Set up the minimal env vars needed by testlyn_api.config.
"""
from __future__ import annotations

import os

os.environ.setdefault("DEV_AUTH_BYPASS", "true")
os.environ.setdefault("RUN_MODE", "docker")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_REGION", "us-central1")
os.environ.setdefault("GCS_SCRIPTS_BUCKET", "test-scripts")
os.environ.setdefault("GCS_RESULTS_BUCKET", "test-results")
os.environ.setdefault("GCS_REPORTS_BUCKET", "test-reports")
os.environ.setdefault("GCP_BQ_DATASET", "testlyn_metrics")
os.environ.setdefault("CLOUD_TASKS_QUEUE", "test-queue")
os.environ.setdefault("API_BASE_URL", "http://testserver")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-firebase")
os.environ.setdefault("WEB_BASE_URL", "http://localhost:3000")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_PLACEHOLDER")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_PLACEHOLDER")
