"""Shared helpers for product scan routes that persist a real TestRun.

Why this exists (review finding): the security / api-contract / synthetic-data
scan routes used to mint a bare ``uuid4`` as the run id with NO ``test_runs``
row behind it. The engine callback ``POST /v1/internal/runs/{id}/complete``
then 404'd and the advertised GET status endpoints could not exist. These
helpers create a real ``TestRun`` (with the correct ``product`` discriminator)
before launch so the run lifecycle works end-to-end.

``test_runs.test_id`` is a non-nullable FK, so a parent ``Test`` row is
required. Scan requests carry only an ``org_id`` — no project / test — so we
attach runs to a per-(project, product) sentinel ``Test`` named
``__<product>_scans__`` inside the org's oldest project (creating an
"Ad-hoc scans" project if the org has none yet). This is documented tech
debt until scan products get first-class Test objects; quota enforcement is
intentionally NOT applied here (scan products have no VU/duration semantics).
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.core.runner import RunnerLaunchResult
from testlyn_api.models.project import Project
from testlyn_api.models.test import Test
from testlyn_api.models.test_run import TestRun

RunStatusLiteral = Literal["queued", "running", "completed", "failed"]


def _sentinel_test_name(product: str) -> str:
    return f"__{product}_scans__"


async def create_scan_run(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    product: str,
    triggered_by: uuid.UUID | None = None,
) -> TestRun:
    """Create + flush a queued TestRun for an ad-hoc product scan.

    Caller is responsible for committing (typically after the runner launch
    succeeds, via :func:`mark_run_launched`).
    """
    from testlyn_api.config import get_settings

    settings = get_settings()

    project = (
        await session.execute(
            select(Project)
            .where(Project.org_id == org_id)
            .order_by(Project.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if project is None:
        project = Project(org_id=org_id, name="Ad-hoc scans", slug="adhoc-scans")
        session.add(project)
        await session.flush()

    name = _sentinel_test_name(product)
    test = (
        await session.execute(
            select(Test)
            .where(
                Test.project_id == project.id,
                Test.product == product,
                Test.name == name,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if test is None:
        test = Test(project_id=project.id, name=name, product=product, config={})
        session.add(test)
        await session.flush()

    run = TestRun(
        test_id=test.id,
        product=product,
        state="queued",
        region=settings.gcp_region,
        triggered_by=triggered_by,
    )
    session.add(run)
    await session.flush()
    return run


def mark_run_launched(run: TestRun, result: RunnerLaunchResult) -> None:
    """Transition a queued scan run to running after a successful launch."""
    run.state = "running"
    run.runner_id = result.runner_id
    run.started_at = result.started_at
    run.region = result.region


def public_status(run: TestRun) -> RunStatusLiteral:
    """Map TestRun.state to the queued|running|completed|failed literal."""
    if run.state in ("queued", "running", "completed", "failed"):
        return run.state  # type: ignore[return-value]
    return "failed"  # cancelled or unknown → terminal failure for scan UIs
