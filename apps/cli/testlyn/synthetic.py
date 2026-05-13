"""testlyn data generate — CLI entry-point for synthetic data generation.

Usage
-----
    testlyn data generate \\
        --schema postgres://user:pass@host/db \\
        --org 00000000-0000-0000-0000-000000000000 \\
        --rows 500 \\
        --output gcs

Environment
-----------
    TESTLYN_API_URL   Base URL of the Testlyn API (default: http://localhost:8000)
    TESTLYN_API_KEY   Bearer token for the API
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any

try:
    import httpx
except ImportError:  # pragma: no cover
    print("httpx is required: pip install httpx", file=sys.stderr)
    raise

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_DEFAULT_API_URL = "http://localhost:8000"


def _api_url() -> str:
    return os.environ.get("TESTLYN_API_URL", _DEFAULT_API_URL).rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("TESTLYN_API_KEY", "")
    h: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ---------------------------------------------------------------------------
# Core command
# ---------------------------------------------------------------------------


def generate(
    *,
    org_id: str,
    schema_dsn: str,
    row_count: int = 100,
    output_mode: str = "gcs",
    gdpr_rules: dict[str, Any] | None = None,
    schema_overrides: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call the Testlyn API to enqueue a synthetic data generation job.

    Returns the parsed JSON response body.
    """
    payload: dict[str, Any] = {
        "org_id": org_id,
        "dsn_secret_id": schema_dsn,
        "row_count": row_count,
        "output_mode": output_mode,
        "gdpr_masking_rules": gdpr_rules or {},
        "schema_overrides": schema_overrides or {},
    }

    url = f"{_api_url()}/v1/products/synthetic-data/generate"
    with httpx.Client(headers=_headers(), timeout=timeout) as client:
        resp = client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# CLI entry-point (minimal argparse — no heavy framework dep)
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="testlyn data generate",
        description="Enqueue a synthetic data generation job via the Testlyn API.",
    )
    parser.add_argument(
        "--schema",
        required=True,
        metavar="DSN",
        help="Postgres DSN or Secret Manager secret ID for the source schema.",
    )
    parser.add_argument(
        "--org",
        required=True,
        metavar="ORG_ID",
        help="Organisation UUID.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=100,
        metavar="N",
        help="Number of rows to generate (1–100000, default 100).",
    )
    parser.add_argument(
        "--output",
        choices=["gcs", "insert"],
        default="gcs",
        help="Output mode: dump to GCS (default) or INSERT into the source DB.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="HTTP request timeout in seconds (default 30).",
    )

    args = parser.parse_args(argv)

    # Validate org_id format early so errors are readable.
    try:
        uuid.UUID(args.org)
    except ValueError:
        parser.error(f"--org must be a valid UUID, got: {args.org!r}")

    result = generate(
        org_id=args.org,
        schema_dsn=args.schema,
        row_count=args.rows,
        output_mode=args.output,
        timeout=args.timeout,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":  # pragma: no cover
    _cli()
