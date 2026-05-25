"""Shared SSRF-safety validation for user-supplied target URLs.

Extracted from ``services/webhooks.py`` so the browser/scanner products
(a11y, api-contract, security) reuse the exact same private/loopback/link-local/
reserved/metadata guard *before* enqueueing jobs that fetch those URLs. Webhook
delivery imports the same helper so there is a single source of truth for the
SSRF policy.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Final
from urllib.parse import urlsplit

# Hosts that must never be reached even if DNS would resolve them to a
# routable IP (defense in depth — covers the GCP metadata server alias).
_BLOCKED_HOSTS: Final[frozenset[str]] = frozenset(
    {"metadata.google.internal", "169.254.169.254"}
)


class UnsafeURL(ValueError):
    """Raised when a target URL fails the SSRF safety check."""


def assert_safe_url(url: str) -> None:
    """Reject URLs that could be used for SSRF.

    Validates the scheme, then resolves the hostname to ALL of its IPs and
    rejects the request if ANY resolved address is private/loopback/link-local/
    reserved/multicast/unspecified (which covers RFC1918, ::1, the
    169.254.169.254 cloud-metadata IP, etc.). Hosts that fail to resolve are
    also rejected.

    KNOWN LIMITATION (DNS rebinding / TOCTOU): we validate the IPs returned by
    getaddrinfo() here, but the eventual consumer (httpx / Playwright / ZAP /
    Schemathesis) re-resolves the hostname when it actually connects, so a
    hostname whose DNS flips between this check and the connect could still
    point at a private IP. Full mitigation requires pinning the connection to a
    validated IP (custom transport) and is tracked separately; this guard
    closes the common direct-IP / static-DNS SSRF vectors.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise UnsafeURL(f"scheme not allowed: {scheme or '(none)'}")

    host = parts.hostname
    if not host:
        raise UnsafeURL("no host in url")

    if host.lower() in _BLOCKED_HOSTS:
        raise UnsafeURL(f"host explicitly blocked: {host}")

    port = parts.port or (443 if scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"host does not resolve: {host}") from exc

    if not infos:
        raise UnsafeURL(f"host does not resolve: {host}")

    for info in infos:
        ip_str = info[4][0]
        ip = ipaddress.ip_address(ip_str)
        # Normalize IPv4-mapped IPv6 (e.g. ::ffff:169.254.169.254) to the
        # embedded IPv4 so the private/link-local checks fire regardless of
        # Python version (IPv6Address.is_private only delegates to the mapped
        # v4 on 3.13+). getattr is None for a plain IPv4Address.
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURL(f"resolved to disallowed ip: {ip_str}")
