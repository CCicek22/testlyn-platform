from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://testlyn:testlyn@localhost:5432/testlyn"
    # Cloud Run wiring: when DB_HOST is set, build database_url from parts +
    # DB_PASSWORD (mounted from Secret Manager). Keeps secrets out of plain env.
    db_host: str = ""
    db_port: int = 5432
    db_name: str = "testlyn"
    db_user: str = "api"
    db_password: str = ""

    @model_validator(mode="after")
    def _compose_database_url(self) -> Settings:
        if self.db_host:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- GCP ---
    gcp_project_id: str = "example-project"
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
    # Comma-separated emails that auto-become owners of bootstrap_org_slug on
    # first signin. Empty in tests + prod-proper; set on dev Cloud Run via env.
    # Stored as string for gcloud --set-env-vars compatibility; split on read.
    bootstrap_admin_emails_raw: str = ""
    bootstrap_org_slug: str = "testlyn-dev"
    bootstrap_org_name: str = "Testlyn Dev"

    @property
    def bootstrap_admin_emails(self) -> list[str]:
        return [e.strip().lower() for e in self.bootstrap_admin_emails_raw.split(",") if e.strip()]

    # --- Mode ---
    run_mode: str = "cloud"  # 'cloud' | 'docker'

    # --- Docs ---
    # Expose /docs, /redoc, /openapi.json. Default True for local + dev; set
    # EXPOSE_DOCS=false in prod to disable all three (returns 404).
    expose_docs: bool = True

    # --- Internal service auth ---
    # Shared secret for /v1/internal/* endpoints (Cloud Tasks → API).
    # Optional in docker mode; required in cloud mode when set.
    internal_token: str = ""

    # --- SCIM ---
    scim_enabled: bool = False
    # Per-org SCIM bearer tokens, sourced from Secret Manager. Format:
    # "<org_uuid>=<token>,<org_uuid>=<token>" (comma-separated pairs). Empty =>
    # SCIM fails closed (rejects every request) even when scim_enabled is True.
    scim_tokens_raw: str = ""

    @property
    def scim_tokens(self) -> dict[str, str]:
        """Parse SCIM_TOKENS_RAW into a {org_id_lower: token} mapping."""
        out: dict[str, str] = {}
        for pair in self.scim_tokens_raw.split(","):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            org_id, _, token = pair.partition("=")
            org_id = org_id.strip().lower()
            token = token.strip()
            if org_id and token:
                out[org_id] = token
        return out

    # --- Web ---
    web_base_url: str = "http://localhost:3000"
    # Allowed CORS origins for browser preflights. Both apex (https://testlyn.example.com)
    # and dev (https://dev.testlyn.example.com) hostnames serve the same deployment; both
    # must be allowed so preflight checks pass. Stored comma-separated for
    # gcloud --update-env-vars compatibility.
    # When empty, falls back to [web_base_url] to preserve local dev and test defaults.
    # Origins are scheme + host + optional port, never a trailing slash: a browser's
    # Origin header carries no path, so "https://testlyn.example.com/" never matches.
    cors_allowed_origins_raw: str = ""

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Parse CORS_ALLOWED_ORIGINS_RAW into a deduplicated list of origins."""
        if not self.cors_allowed_origins_raw.strip():
            return [self.web_base_url]
        seen: set[str] = set()
        out: list[str] = []
        for item in self.cors_allowed_origins_raw.split(","):
            origin = item.strip()
            if origin and origin not in seen:
                seen.add(origin)
                out.append(origin)
        return out if out else [self.web_base_url]

    # --- Gemini / Vertex AI ---
    gemini_model: str = "gemini-3.1-flash-lite"
    vertex_ai_location: str = "us-central1"

    # --- Chat (in-process ADK coordinator + sub-agents) ---
    # Gemini 3.x preview models are served only from the Vertex "global"
    # endpoint (404 in regional locations); api's own Vertex calls keep
    # vertex_ai_location=us-central1 and pass location explicitly, so these
    # never collide.
    chat_gemini_model: str = "gemini-3.1-flash-lite-preview"
    chat_vertex_location: str = "global"
    chat_app_name: str = "testlyn-chat"
    # Loopback to api's own port; chat tools call /v1/* with the user's bearer
    # token so the API's auth/RBAC/audit/rate-limit still fire (Option A).
    chat_api_base: str = "http://127.0.0.1:8080"
    chat_upstream_timeout_s: float = 30.0
    chat_upstream_connect_timeout_s: float = 5.0
    chat_use_redis_session: bool = False

    # --- Knowledge store (embeddings) ---
    # "hashing" is an offline lexical stand-in (default, tests, CI).
    # "openai_compat" calls an OpenAI-style /v1/embeddings endpoint.
    knowledge_embedding_provider: Literal["hashing", "openai_compat"] = "hashing"
    knowledge_embedding_base_url: str = ""
    knowledge_embedding_model: str = "embeddinggemma"
    knowledge_embedding_api_key: str = ""
    knowledge_embedding_timeout_s: float = 30.0
    knowledge_embedding_batch_size: int = 32
    knowledge_max_document_chars: int = 500_000

    # --- Stripe ---
    stripe_secret_key: str = "sk_test_PLACEHOLDER"
    stripe_webhook_secret: str = "whsec_PLACEHOLDER"
    # Price-id → plan mapping. Read by stripe_webhook to translate a
    # subscription item's price id into a Testlyn plan slug. Empty in
    # tests + local dev; populated via env / Secret Manager in cloud.
    stripe_price_hobby: str = ""
    stripe_price_pro: str = ""
    stripe_price_business: str = ""

    # --- k6 ---
    k6_image_tag: str = "grafana/k6:1.3.0"

    # --- Functional / Locator Healer ---
    locator_healer_url: str = "http://localhost:8090"

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
    def _knowledge_embedder_needs_url(self) -> Settings:
        if self.knowledge_embedding_provider == "openai_compat" and not self.knowledge_embedding_base_url:
            raise ValueError("knowledge_embedding_base_url is required when provider is openai_compat")
        return self

    @model_validator(mode="after")
    def _no_bypass_in_cloud(self) -> Settings:
        if self.dev_auth_bypass and self.run_mode == "cloud":
            raise ValueError("dev_auth_bypass must not be True when run_mode='cloud'")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
