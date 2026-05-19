"""Pydantic Settings for testlyn-chat.

All knobs come from env. Secret Manager values are mounted as env vars by
Cloud Run; we never read raw API keys (see CLAUDE.md §2 rule 5 / rule 12).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Upstream Testlyn API ------------------------------------------------
    # The chat service is a thin orchestration layer; all business logic stays
    # in testlyn-api. We call /v1/* on the user's behalf with their Firebase
    # bearer token.
    testlyn_api_base: str = Field(
        default="http://localhost:8000",
        description="Base URL of testlyn-api (no trailing slash).",
    )

    # --- Vertex AI / Gemini --------------------------------------------------
    vertex_project: str = Field(default="example-project")
    vertex_location: str = Field(default="us-central1")
    gemini_model: str = Field(default="gemini-3.1-flash-lite-preview")

    # --- Auth -----------------------------------------------------------------
    firebase_project_id: str = Field(default="example-project")

    # --- Session store -------------------------------------------------------
    # In-memory for dev, Redis for prod. URL ignored when use_redis_session=False.
    # Dragonfly DB 1 reserved for testlyn-chat (Terraform + CI agree).
    redis_url: str = Field(default="redis://10.0.0.5:6379/1")
    use_redis_session: bool = Field(default=False)

    # --- CORS / SSE ----------------------------------------------------------
    web_base_url: str = Field(default="http://localhost:3000")

    # --- HTTP client ---------------------------------------------------------
    upstream_timeout_s: float = Field(default=30.0)
    upstream_connect_timeout_s: float = Field(default=5.0)

    # --- App identity --------------------------------------------------------
    app_name: str = Field(default="testlyn-chat")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
