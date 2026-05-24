"""Verify that startup configures google-genai to use the Vertex AI backend.

The ADK agents call Gemini via the google-genai Client, which selects the
Vertex backend only when these three env vars are present:
  - GOOGLE_GENAI_USE_VERTEXAI
  - GOOGLE_CLOUD_PROJECT
  - GOOGLE_CLOUD_LOCATION

Without them the client falls back to the Developer API and raises
``ValueError: No API key was provided.`` (CLAUDE.md §2 rule 5 forbids API keys).

These tests verify that `configure_vertex_backend` sets the vars from
Settings before any ADK agent / genai Client is constructed.
"""

from __future__ import annotations

import os

import pytest


_VARS = ("GOOGLE_GENAI_USE_VERTEXAI", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")


@pytest.fixture(autouse=True)
def _clean_genai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove the three Vertex env vars so each test starts from a clean slate."""
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)


def test_vertex_env_vars_set_after_configure(monkeypatch: pytest.MonkeyPatch) -> None:
    """configure_vertex_backend() must set all three vars from Settings."""
    from testlyn_chat.config import get_settings
    from testlyn_chat.main import configure_vertex_backend

    settings = get_settings()
    configure_vertex_backend(settings)

    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") in {"true", "1"}, (
        "GOOGLE_GENAI_USE_VERTEXAI must be truthy after configure_vertex_backend()"
    )
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == settings.vertex_project
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == settings.vertex_location


def test_vertex_env_vars_match_settings_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Project and location come from Settings, not hardcoded strings."""
    monkeypatch.setenv("VERTEX_PROJECT", "my-custom-project")
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west1")

    # Clear the lru_cache so Settings re-reads the patched env.
    from testlyn_chat.config import get_settings
    get_settings.cache_clear()

    settings = get_settings()

    from testlyn_chat.main import configure_vertex_backend
    configure_vertex_backend(settings)

    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "my-custom-project"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "europe-west1"


def test_explicit_external_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    """setdefault() must NOT override an explicitly set external env var."""
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "external-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-east1")

    from testlyn_chat.config import get_settings
    from testlyn_chat.main import configure_vertex_backend

    configure_vertex_backend(get_settings())

    # External values must survive.
    assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "1"
    assert os.environ["GOOGLE_CLOUD_PROJECT"] == "external-project"
    assert os.environ["GOOGLE_CLOUD_LOCATION"] == "us-east1"
