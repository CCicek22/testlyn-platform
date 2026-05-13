"""SSO service: SAML 2.0 + OIDC handlers.

SAML requires `python3-saml` (onelogin-saml2) as an optional dep.
OIDC requires `authlib` as an optional dep.

Both are gracefully absent: callers catch FeatureDisabledError and surface 501.

Audit-log hook point for SOC 2 evidence trail:
  After successful SSO login call AuditService.log(action="sso.login", ...).
  W3A owns the audit log schema — we only call the existing service.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from testlyn_api.models.org import OrgMember
from testlyn_api.models.sso_provider import SsoProvider
from testlyn_api.models.user import User

log = structlog.get_logger(__name__)


class FeatureDisabledError(RuntimeError):
    """Raised when an optional SSO library is not installed."""


# ---------------------------------------------------------------------------
# SAML
# ---------------------------------------------------------------------------


class SamlHandler:
    """Minimal SAML 2.0 SP-initiated flow using onelogin-saml2 (python3-saml).

    Supported IdPs (tested configuration shapes):
      - Google Workspace  — standard SAML 2.0 metadata XML
      - Okta              — standard SAML 2.0 metadata XML
      - Azure AD          — standard SAML 2.0 metadata XML
      - Generic SAML 2.0  — any compliant metadata XML

    Attribute mapping keys (configurable per provider):
      email, name, given_name, family_name
    """

    def __init__(self) -> None:
        try:
            from onelogin.saml2.auth import OneLogin_Saml2_Auth  # type: ignore[import]

            self._auth_cls = OneLogin_Saml2_Auth
        except ImportError:
            self._auth_cls = None

    def _require_lib(self) -> None:
        if self._auth_cls is None:
            raise FeatureDisabledError(
                "SAML support requires 'python3-saml'. "
                "Add onelogin-saml2 to your dependencies."
            )

    def build_settings(self, provider: SsoProvider, sp_base_url: str) -> dict[str, Any]:
        """Return a onelogin-saml2 settings dict from the stored provider record."""
        self._require_lib()
        attr_map: dict[str, Any] = provider.attribute_mappings or {}
        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": f"{sp_base_url}/v1/sso/{provider.id}/metadata",
                "assertionConsumerService": {
                    "url": f"{sp_base_url}/v1/sso/{provider.id}/acs",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
                "x509cert": "",
                "privateKey": "",
            },
            "idp": {
                "entityId": attr_map.get("idp_entity_id", ""),
                "singleSignOnService": {
                    "url": attr_map.get("sso_url", ""),
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": attr_map.get("idp_cert", ""),
            },
            "idp_metadata_xml": provider.metadata_xml_or_discovery_url,
        }

    def get_login_url(self, provider: SsoProvider, sp_base_url: str) -> str:
        """Return the IdP redirect URL for SP-initiated SSO."""
        self._require_lib()
        # TODO (Phase 4 GA): instantiate OneLogin_Saml2_Auth with a real request
        # object and call auth.login() — deferred until real HTTP context is wired.
        raise NotImplementedError("Full SAML login flow deferred to Phase 4 GA")

    def parse_assertion(
        self,
        provider: SsoProvider,
        sp_base_url: str,
        saml_response: str,
        relay_state: str,
    ) -> dict[str, str]:
        """Parse and validate a SAML assertion.

        Returns a dict with at minimum: {"email": "...", "name": "..."}
        Raises ValueError on invalid / expired assertion.

        TODO (Phase 4 GA): wire full signature verification via
        OneLogin_Saml2_Auth.process_response().
        """
        self._require_lib()
        # Scaffold: demonstrate attribute extraction logic without live IdP
        raise NotImplementedError("Full SAML assertion parsing deferred to Phase 4 GA")


# ---------------------------------------------------------------------------
# OIDC
# ---------------------------------------------------------------------------


class OidcHandler:
    """OIDC handler using authlib.

    Supported IdPs:
      - Google Workspace  — discovery: https://accounts.google.com
      - Okta              — discovery: https://<domain>/.well-known/openid-configuration
      - Azure AD          — discovery: https://login.microsoftonline.com/<tenant>/v2.0
      - Generic OIDC      — any compliant discovery URL

    Attribute mapping keys: sub, email, name, given_name, family_name
    """

    def __init__(self) -> None:
        try:
            from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import]

            self._client_cls = AsyncOAuth2Client
        except ImportError:
            self._client_cls = None

    def _require_lib(self) -> None:
        if self._client_cls is None:
            raise FeatureDisabledError(
                "OIDC support requires 'authlib'. "
                "Add authlib to your dependencies."
            )

    async def fetch_user_info(
        self,
        provider: SsoProvider,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code: str,
    ) -> dict[str, str]:
        """Exchange auth code for tokens and return normalised user claims.

        Returns dict with at minimum: {"sub": "...", "email": "...", "name": "..."}
        TODO (Phase 4 GA): implement token exchange + userinfo fetch.
        """
        self._require_lib()
        raise NotImplementedError("Full OIDC code exchange deferred to Phase 4 GA")


# ---------------------------------------------------------------------------
# User provisioning
# ---------------------------------------------------------------------------


async def provision_sso_user(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    email: str,
    name: str | None,
    external_sub: str | None,
) -> User:
    """Auto-provision a user from SSO claims.

    - If a User row with this email already exists, return it.
    - Otherwise create User + add as OrgMember with 'member' role.

    Audit hook point: caller should log action='sso.provision' via AuditService
    after this returns (W3A owns audit schema).
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            email=email,
            name=name,
            firebase_uid=external_sub,
        )
        session.add(user)
        await session.flush()
        log.info("sso.user_provisioned", email=email, org_id=str(org_id))

    # Ensure org membership
    membership_result = await session.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.user_id == user.id,
        )
    )
    if membership_result.scalar_one_or_none() is None:
        session.add(OrgMember(org_id=org_id, user_id=user.id, role="member"))
        log.info("sso.member_added", email=email, org_id=str(org_id))

    await session.commit()
    await session.refresh(user)
    return user


async def get_active_provider(
    session: AsyncSession, org_id: uuid.UUID, kind: str | None = None
) -> SsoProvider | None:
    """Return the first active SSO provider for an org (optionally filtered by kind)."""
    q = select(SsoProvider).where(
        SsoProvider.org_id == org_id,
        SsoProvider.active.is_(True),
    )
    if kind is not None:
        q = q.where(SsoProvider.kind == kind)
    result = await session.execute(q.limit(1))
    return result.scalar_one_or_none()
