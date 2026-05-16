"""Idempotent Firebase Admin SDK initialization.

`firebase_admin.auth.verify_id_token` requires an initialized default app.
On Cloud Run with Workload Identity the default credentials are picked up
from the runtime service account — no key file needed. `project_id` is
explicit because the metadata-server-derived project is not always the same
as the Identity Platform tenant project.
"""

from __future__ import annotations

import structlog

from testlyn_api.config import get_settings

log = structlog.get_logger(__name__)


def init_firebase() -> None:
    """Initialize the default Firebase app once; subsequent calls are no-ops."""
    settings = get_settings()
    if settings.dev_auth_bypass:
        log.info("firebase.init.skipped", reason="dev_auth_bypass")
        return

    import firebase_admin

    if firebase_admin._apps:
        return

    project_id = settings.firebase_project_id or settings.gcp_project_id
    if not project_id:
        log.warning("firebase.init.skipped", reason="no_project_id")
        return

    firebase_admin.initialize_app(options={"projectId": project_id})
    log.info("firebase.init.ok", project_id=project_id)
