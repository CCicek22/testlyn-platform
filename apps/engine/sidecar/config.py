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

    # Parser dispatch — "k6" (default), "axe", or "playwright".  Determines
    # which Parser implementation the sidecar instantiates in main.py.
    PARSER: str = Field(default="k6")

    # Unified input path used by every parser.  Phase-1 keeps K6_OUTPUT_PATH
    # as a back-compat alias; if INPUT_PATH is unset, the property
    # `input_path` falls back to K6_OUTPUT_PATH (k6) or the named pipe
    # convention for other engines.
    INPUT_PATH: str | None = Field(default=None)

    # k6 JSONL input path (named pipe or regular file).  Kept for back-compat;
    # new code should read `cfg.input_path` (property below).
    K6_OUTPUT_PATH: str = Field(default="/tmp/k6.jsonl")

    # Path to k6's --summary-export JSON (written by entrypoint.sh after k6
    # finishes).  Used by `write_runs_summary` to populate spec §5 columns
    # (vus_max / iterations / http_reqs / http_failed / data_sent / data_received).
    # If absent or unreadable, those columns are written as NULL.
    K6_SUMMARY_PATH: str = Field(default="/tmp/work/summary.json")

    # Path the engine entrypoint writes the k6/playwright exit code to AFTER
    # the workload exits.  The sidecar polls this file before writing
    # runs_summary so the env-var-at-startup race is gone.
    EXIT_CODE_PATH: str = Field(default="/tmp/k6_exit_code")

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

    @property
    def input_path(self) -> str:
        """Resolved input path for the parser.

        Precedence: explicit INPUT_PATH → K6_OUTPUT_PATH (back-compat).
        """
        return self.INPUT_PATH or self.K6_OUTPUT_PATH
