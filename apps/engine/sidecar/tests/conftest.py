"""Shared pytest fixtures for the sidecar test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Set required env vars before any config import
os.environ.setdefault("RUN_ID", "test-run-id")
os.environ.setdefault("ORG_ID", "test-org-id")
os.environ.setdefault("GCP_PROJECT", "test-project")


@pytest.fixture
def k6_fixture_path() -> Path:
    return FIXTURES_DIR / "k6.jsonl"
