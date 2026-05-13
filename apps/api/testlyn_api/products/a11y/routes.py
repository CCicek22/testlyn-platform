from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, status

from testlyn_api.deps import CurrentUserDep, SessionDep
from testlyn_api.products.a11y.runner import A11yRunner
from testlyn_api.products.a11y.schemas import (
    A11yAuditRequest,
    A11yRecipeCreate,
    A11yRecipeOut,
    A11yReport,
    A11ySummary,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/products/a11y", tags=["a11y"])
runs_router = APIRouter(prefix="/v1/runs", tags=["a11y"])

_runner = A11yRunner()


@router.post("/audit", status_code=status.HTTP_202_ACCEPTED)
async def one_shot_audit(
    body: A11yAuditRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, Any]:
    """
    Enqueue a one-shot WCAG 2.2 accessibility audit.

    Returns immediately with the runner_id; poll
    GET /v1/runs/:id/violations for results.
    """
    result = await _runner.launch(
        test_run_id=body.test_run_id,
        script_uri="",  # a11y runner uses AUDIT_CONFIG_URI from env
        vus=1,
        duration_seconds=300,
        env={
            "AUDIT_URLS": ",".join(str(u) for u in body.config.urls),
            "MAX_DEPTH": str(body.config.max_depth),
            "WCAG_TAGS": ",".join(body.config.wcag_tags),
        },
    )
    log.info(
        "a11y.audit.enqueued",
        run_id=str(body.test_run_id),
        user_id=str(current_user.id),
        runner_id=result.runner_id,
    )
    return {
        "run_id": str(body.test_run_id),
        "runner_id": result.runner_id,
        "started_at": result.started_at.isoformat(),
        "region": result.region,
    }


@router.post("/recipes", status_code=status.HTTP_201_CREATED, response_model=A11yRecipeOut)
async def create_recipe(
    body: A11yRecipeCreate,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> A11yRecipeOut:
    """
    Create an a11y audit recipe (scheduled or on-demand).

    Persisted to the a11y_audit_recipes Postgres table (added by migration 0005).
    If schedule_cron is set, a Cloud Scheduler job should be created separately
    via the infra/terraform/modules/cloud_scheduler module.

    TODO(W2C): wire Cloud Scheduler creation when schedule_cron is non-null.
    """
    from sqlalchemy import text

    recipe_id = uuid.uuid4()
    now = datetime.now(tz=UTC)
    urls_json = [str(u) for u in body.urls]

    await session.execute(
        text(
            """
            INSERT INTO a11y_audit_recipes
                (id, target_id, urls, max_depth, schedule_cron, created_at, updated_at)
            VALUES
                (:id, :target_id, :urls::jsonb, :max_depth, :schedule_cron, :created_at, :updated_at)
            """
        ),
        {
            "id": recipe_id,
            "target_id": body.target_id,
            "urls": __import__("json").dumps(urls_json),
            "max_depth": body.max_depth,
            "schedule_cron": body.schedule_cron,
            "created_at": now,
            "updated_at": now,
        },
    )
    await session.commit()

    log.info(
        "a11y.recipe.created",
        recipe_id=str(recipe_id),
        user_id=str(current_user.id),
    )

    return A11yRecipeOut(
        id=recipe_id,
        target_id=body.target_id,
        urls=urls_json,
        max_depth=body.max_depth,
        schedule_cron=body.schedule_cron,
        created_at=now,
        updated_at=now,
    )


@runs_router.get("/{run_id}/violations", response_model=A11yReport)
async def get_violations(
    run_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> A11yReport:
    """
    Return violations for a completed a11y run.

    Violations are queried from BigQuery via the API (no client-side BQ access).

    TODO(W2C): implement BQ query for violations — requires engine-a11y to be
    deployed and BigQuery table populated. Returning stub for now.
    """
    log.info("a11y.violations.get", run_id=str(run_id), user_id=str(current_user.id))

    # Stub: return empty report. Real implementation queries BQ via
    # testlyn_api.products.a11y.bq_queries (to be added when engine ships).
    return A11yReport(
        run_id=run_id,
        product="a11y",
        summary=A11ySummary(total=0, critical=0, serious=0, moderate=0, minor=0),
        violations=[],
        pdf_uri=None,
        created_at=datetime.now(tz=UTC),
    )
