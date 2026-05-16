from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, status

from testlyn_api.core.permissions import _enforce_perm
from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.synthetic_data.runner import SyntheticDataRunner
from testlyn_api.products.synthetic_data.schemas import GenerateRequest, GenerateResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/products/synthetic-data", tags=["synthetic_data"])

_runner = SyntheticDataRunner()


@router.post(
    "/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=GenerateResponse,
)
async def generate(
    body: GenerateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> GenerateResponse:
    """
    Enqueue a synthetic data generation job.

    Returns immediately with job_id. Poll
    GET /v1/products/synthetic-data/jobs/{job_id} for status.

    The runner fetches the Postgres DSN from Secret Manager (dsn_secret_id),
    reflects the schema, generates Faker rows respecting gdpr_masking_rules,
    and writes to GCS or inserts directly based on output_mode.
    """
    # Verify caller belongs to body.org_id — otherwise an authenticated user
    # could trigger synthetic-data jobs (and bill) against another tenant.
    await _enforce_perm(
        "run",
        "test",
        user_id=current_user.id,
        org_id=body.org_id,
        session=session,
    )

    job_id = uuid.uuid4()

    result = await _runner.launch(
        test_run_id=job_id,
        script_uri="",
        vus=1,
        duration_seconds=300,
        env={
            "DSN_SECRET_ID": body.dsn_secret_id,
            "ROW_COUNT": str(body.row_count),
            "OUTPUT_MODE": body.output_mode,
            "SCHEMA_OVERRIDES": _json_env(body.schema_overrides),
            "GDPR_MASKING_RULES": _json_env(body.gdpr_masking_rules),
        },
    )

    log.info(
        "synthetic_data.generate.enqueued",
        job_id=str(job_id),
        org_id=str(body.org_id),
        user_id=str(current_user.id),
        runner_id=result.runner_id,
    )

    # Stub GCS URI for docker/stub mode
    dump_uri: str | None = None
    if result.runner_id.startswith("synth-docker-stub-"):
        dump_uri = f"gs://testlyn-prod-results/synthetic-data/{job_id}/sample.sql"

    return GenerateResponse(
        job_id=job_id,
        status="queued",
        dump_gcs_uri=dump_uri,
    )


def _json_env(obj: Any) -> str:
    import json

    return json.dumps(obj)
