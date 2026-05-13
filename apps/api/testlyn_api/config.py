from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://testlyn:testlyn@localhost:5432/testlyn"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- GCP ---
    gcp_project_id: str = "example-project-prod"
    gcp_region: str = "us-central1"
    gcs_scripts_bucket: str = "testlyn-prod-scripts"
    gcs_results_bucket: str = "testlyn-prod-results"
    gcs_reports_bucket: str = "testlyn-prod-reports"
    gcp_bq_dataset: str = "testlyn_metrics"

    # --- Cloud Tasks ---
    cloud_tasks_queue: str = "testlyn-run-queue"
    api_base_url: str = "http://localhost:8080"

    # --- Firebase / Identity Platform ---
    firebase_project_id: str = ""

    # --- Auth ---
    dev_auth_bypass: bool = False

    # --- Mode ---
    run_mode: str = "cloud"  # 'cloud' | 'docker'

    # --- Internal service auth ---
    # Shared secret for /v1/internal/* endpoints (Cloud Tasks → API).
    # Optional in docker mode; required in cloud mode when set.
    internal_token: str = ""

    # --- SCIM ---
    scim_enabled: bool = False

    # --- Web ---
    web_base_url: str = "http://localhost:3000"

    # --- Gemini / Vertex AI ---
    gemini_model: str = "gemini-3.1-flash-lite"
    vertex_ai_location: str = "us-central1"

    # --- Stripe ---
    stripe_secret_key: str = "sk_test_PLACEHOLDER"
    stripe_webhook_secret: str = "whsec_PLACEHOLDER"

    # --- k6 ---
    k6_image_tag: str = "grafana/k6:1.3.0"

    # --- SSE ---
    sse_heartbeat_interval: float = 10.0
    # 0 = unlimited (production default); set to a small number in tests to cap stream length
    sse_max_ticks: int = 0

    @field_validator("run_mode")
    @classmethod
    def validate_run_mode(cls, v: str) -> str:
        if v not in {"cloud", "docker"}:
            raise ValueError("run_mode must be 'cloud' or 'docker'")
        return v

    @model_validator(mode="after")
    def _no_bypass_in_cloud(self) -> Settings:
        if self.dev_auth_bypass and self.run_mode == "cloud":
            raise ValueError("dev_auth_bypass must not be True when run_mode='cloud'")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
