"""Regression test: verify_token must NOT pass check_revoked=True.

On Cloud Run the firebase_admin.auth.verify_id_token(..., check_revoked=True)
call triggers an extra Identity Toolkit accounts:lookup RPC which Cloud Run's
service account lacks permission for. The broad except swallows it → every
valid token 401s.

Fix: drop check_revoked (matches the API service's accepted posture; staleness
is bounded by the 60s cache TTL).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_auth_state(monkeypatch):
    """Reset module-level singletons so tests are independent."""
    import testlyn_chat.auth as auth_mod

    # Clear the LRU cache between tests so cache hits don't mask real calls.
    auth_mod._cache.clear()
    # Reset init flag so _ensure_firebase_init would re-run (we stub it below).
    monkeypatch.setattr(auth_mod, "_firebase_initialised", True)
    yield
    auth_mod._cache.clear()


def test_verify_token_does_not_pass_check_revoked(monkeypatch):
    """A token that raises when check_revoked=True is passed MUST succeed.

    Before the fix verify_token forwards check_revoked=True, triggering the
    privileged accounts:lookup → PermissionError → caught → returns None.
    After the fix the flag is absent; the fake returns valid claims.
    """
    import firebase_admin.auth as fb_auth

    import testlyn_chat.auth as auth_mod

    # Use a unique token so no prior cache entry can exist.
    TOKEN = "good-token-unique-abc123"  # noqa: N806

    def fake_verify_id_token(token, **kwargs):
        if kwargs.get("check_revoked"):
            raise PermissionError(
                "identitytoolkit accounts:lookup denied — missing IAM permission"
            )
        return {"uid": "u1", "sub": "u1"}

    monkeypatch.setattr(fb_auth, "verify_id_token", fake_verify_id_token)

    result = auth_mod.verify_token(TOKEN)

    assert result is not None, (
        "verify_token returned None — likely still passing check_revoked=True, "
        "which raises PermissionError and is swallowed, causing every valid token to 401"
    )
    assert result["uid"] == "u1"
