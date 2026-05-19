"""Shared pytest fixtures for testlyn-chat."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Force deterministic, offline-friendly settings BEFORE the package is imported.
os.environ.setdefault("TESTLYN_API_BASE", "http://api.test")
os.environ.setdefault("VERTEX_PROJECT", "test-project")
os.environ.setdefault("VERTEX_LOCATION", "us-central1")
os.environ.setdefault("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("WEB_BASE_URL", "http://localhost:3000")
os.environ.setdefault("USE_REDIS_SESSION", "false")


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    """Ensure every test sees a fresh Settings instance."""
    from testlyn_chat.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
