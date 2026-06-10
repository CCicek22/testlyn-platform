"""SSRF guard for webhook delivery (_assert_safe_url / _post)."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, patch

import pytest
from testlyn_api.services import webhooks
from testlyn_api.services.webhooks import (
    UnsafeWebhookURL,
    _assert_safe_url,
    _post,
)


def _addrinfo(ip: str, port: int = 443):
    """Build a getaddrinfo()-shaped result for a single IPv4 address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


# ─── _assert_safe_url: rejections ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://172.16.0.1/x",
        "http://[::1]/x",
        "http://169.254.1.2/x",  # link-local range
    ],
)
def test_assert_safe_url_rejects_private_ip_literals(url: str) -> None:
    # IP literals: getaddrinfo returns the literal back, no real DNS needed.
    with pytest.raises(UnsafeWebhookURL):
        _assert_safe_url(url)


def test_assert_safe_url_rejects_metadata_ip() -> None:
    # 169.254.169.254 is caught both by the explicit blocklist and link-local.
    with pytest.raises(UnsafeWebhookURL):
        _assert_safe_url("http://169.254.169.254/computeMetadata/v1/")


def test_assert_safe_url_rejects_metadata_hostname() -> None:
    # Explicit hostname blocklist — must reject before any DNS resolution.
    with pytest.raises(UnsafeWebhookURL):
        _assert_safe_url("http://metadata.google.internal/x")


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://127.0.0.1/x",
        "ftp://example.com/x",
    ],
)
def test_assert_safe_url_rejects_non_http_schemes(url: str) -> None:
    with pytest.raises(UnsafeWebhookURL):
        _assert_safe_url(url)


def test_assert_safe_url_rejects_unresolvable_host() -> None:
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("nope")):
        with pytest.raises(UnsafeWebhookURL):
            _assert_safe_url("http://does-not-exist.invalid/x")


def test_assert_safe_url_rejects_public_host_that_resolves_private() -> None:
    # A public-looking hostname that DNS resolves to a private IP must fail.
    with patch("socket.getaddrinfo", return_value=_addrinfo("10.1.2.3")):
        with pytest.raises(UnsafeWebhookURL):
            _assert_safe_url("http://evil.example.com/x")


def _addrinfo6(ip: str, port: int = 443):
    """Build a getaddrinfo()-shaped result for a single IPv6 address."""
    return [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port, 0, 0))]


@pytest.mark.parametrize(
    "mapped_ip",
    [
        "::ffff:169.254.169.254",  # IPv4-mapped metadata IP
        "::ffff:10.0.0.1",  # IPv4-mapped RFC1918
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
    ],
)
def test_assert_safe_url_rejects_ipv4_mapped_ipv6(mapped_ip: str) -> None:
    # A host resolving to an IPv4-mapped IPv6 address must be rejected via the
    # ipv4_mapped unwrap — independent of the Python version's is_private impl.
    with patch("socket.getaddrinfo", return_value=_addrinfo6(mapped_ip)):
        with pytest.raises(UnsafeWebhookURL):
            _assert_safe_url("http://evil.example.com/x")


# ─── _assert_safe_url: allow ──────────────────────────────────────────────────


def test_assert_safe_url_allows_public_host() -> None:
    # Mock DNS so the test is hermetic / offline.
    with patch("socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        _assert_safe_url("https://example.com/hook")  # must not raise


# ─── _post: blocked URLs return False + log + never hit the network ────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/computeMetadata/v1/",
        "http://127.0.0.1/x",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://metadata.google.internal/x",
        "file:///etc/passwd",
    ],
)
async def test_post_blocks_unsafe_url(url: str) -> None:
    with patch.object(webhooks, "log") as mock_log:
        with patch("httpx.AsyncClient") as mock_client:
            result = await _post(
                url=url, body=b"{}", signature="sha256=x", delivery_id="d1"
            )

    assert result is False
    # No httpx client should ever be constructed for a blocked URL.
    mock_client.assert_not_called()
    # ssrf_blocked must be logged.
    logged_events = [c.args[0] for c in mock_log.warning.call_args_list if c.args]
    assert "webhooks.ssrf_blocked" in logged_events


@pytest.mark.asyncio
async def test_post_allows_public_url() -> None:
    resp = AsyncMock()
    resp.is_success = True

    class _FakeClient:
        def __init__(self, *a, **k):
            self.kwargs = k

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return resp

    with patch("socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        with patch("httpx.AsyncClient", _FakeClient):
            result = await _post(
                url="https://example.com/hook",
                body=b"{}",
                signature="sha256=x",
                delivery_id="d1",
            )

    assert result is True


@pytest.mark.asyncio
async def test_post_disables_redirect_following() -> None:
    captured: dict = {}

    class _FakeClient:
        def __init__(self, *a, **k):
            captured.update(k)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            r = AsyncMock()
            r.is_success = True
            return r

    with patch("socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        with patch("httpx.AsyncClient", _FakeClient):
            await _post(
                url="https://example.com/hook",
                body=b"{}",
                signature="sha256=x",
                delivery_id="d1",
            )

    assert captured.get("follow_redirects") is False


# ─── assert_safe_url_async: same policy, off-loop DNS ─────────────────────────


@pytest.mark.asyncio
async def test_assert_safe_url_async_rejects_metadata_ip() -> None:
    from testlyn_api.core.url_safety import UnsafeURL, assert_safe_url_async

    with pytest.raises(UnsafeURL):
        await assert_safe_url_async("http://169.254.169.254/computeMetadata/v1/")


@pytest.mark.asyncio
async def test_assert_safe_url_async_allows_public_host() -> None:
    from testlyn_api.core.url_safety import assert_safe_url_async

    with patch("socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")):
        await assert_safe_url_async("https://example.com/hook")  # must not raise
