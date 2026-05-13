"""Environment-driven configuration for the BQ sidecar.

All settings come from env vars — no config files (per spec §10).
Secrets go through Secret Manager + Workload Identity if added later.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SidecarConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=True)

    # --- required ---
    RUN_ID: str = Field(..., description="Injected by Cloud Run Job invoker")
    ORG_ID: str = Field(..., description="Injected by Cloud Run Job invoker")
    GCP_PROJECT: str = Field(..., description="Example Co GCP project ID")

    # --- optional with defaults ---
    PRODUCT: str = Field(
        default="load", description="Product discriminator; Phase 1 hardcodes 'load'"
    )
    REGION: str = Field(default="us-central1")
    BQ_DATASET: str = Field(default="testlyn_metrics")
    BQ_SAMPLES_TABLE: str = Field(default="samples_1s")
    BQ_SUMMARY_TABLE: str = Field(default="runs_summary")

    # k6 JSONL input path (named pipe or regular file)
    K6_OUTPUT_PATH: str = Field(default="/tmp/k6.jsonl")

    # Aggregation
    WINDOW_SECONDS: int = Field(default=1, ge=1)

    # Batching / flush
    BATCH_SIZE: int = Field(default=5000, ge=1, le=50000)
    FLUSH_INTERVAL_SECONDS: float = Field(default=5.0, gt=0)
    MAX_BUFFER_ROWS: int = Field(default=50000, ge=1)

    # Tag grouping
    TAG_GROUPING_PROFILE: str = Field(default="default")

    # Spool
    SPOOL_DIR: str = Field(default="/tmp/spool")
    SPOOL_GCS_BUCKET: str = Field(default="testlyn-prod-spool")
    SPOOL_MAX_BYTES: int = Field(default=1 * 1024 * 1024 * 1024)  # 1 GiB

    # BQ emulator (local dev)
    BIGQUERY_EMULATOR_HOST: str | None = Field(default=None)

    # Health server
    HEALTH_PORT: int = Field(default=8081)

    # Logging
    LOG_LEVEL: str = Field(default="INFO")

    @property
    def samples_table_id(self) -> str:
        return f"{self.GCP_PROJECT}.{self.BQ_DATASET}.{self.BQ_SAMPLES_TABLE}"

    @property
    def summary_table_id(self) -> str:
        return f"{self.GCP_PROJECT}.{self.BQ_DATASET}.{self.BQ_SUMMARY_TABLE}"
