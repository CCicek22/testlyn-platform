from __future__ import annotations

from testlyn_api.core.runner import RunnerStatus


def derive_state(execution: object) -> str:
    """Derive a canonical run state string from a Cloud Run Execution object.

    Cloud Run v2 `execution.reconciling` is a bool flag indicating whether the
    control plane is currently reconciling desired vs actual state — it is NOT
    an execution status and must never be used as a state discriminator.

    This helper reads the task-count fields that *do* reflect execution outcome.
    """
    succeeded: int = getattr(execution, "succeeded_count", 0) or 0
    failed: int = getattr(execution, "failed_count", 0) or 0
    cancelled: int = getattr(execution, "cancelled_count", 0) or 0
    running: int = getattr(execution, "running_count", 0) or 0

    if succeeded > 0:
        return "completed"
    if failed > 0:
        return "failed"
    if cancelled > 0:
        return "cancelled"
    if running > 0:
        return "running"
    return "queued"


def execution_to_status(execution: object) -> RunnerStatus:
    """Convert a Cloud Run Execution object to a RunnerStatus."""
    return RunnerStatus(
        state=derive_state(execution),
        started_at=getattr(execution, "start_time", None),
        finished_at=getattr(execution, "completion_time", None),
        exit_reason=None,
    )
