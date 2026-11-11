"""Address-policy and redirect tests that never contact the refused hosts."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import pytest

from templeos import public_http
from templeos.public_http import UnsafeURL, is_allowed_ip, normalize_ip, resolve_host, resolve_url, split_url


def _info(ip: str, port: int = 443) -> tuple:
    addr = ipaddress.ip_address(ip)
    family = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
    sockaddr = (ip, port) if addr.version == 4 else (ip, port, 0, 0)
    return (family, socket.SOCK_STREAM, 6, "", sockaddr)


def test_split_url_rejects_credentials_and_non_http():
    with pytest.raises(UnsafeURL):
        split_url("https://user:pass@example.com/x")
    with pytest.raises(UnsafeURL):
        split_url("file:///etc/passwd")
    with pytest.raises(UnsafeURL):
        split_url("ftp://example.com/x")


def test_is_allowed_ip_policies():
    assert is_allowed_ip(ipaddress.ip_address("8.8.8.8")) is True
    assert is_allowed_ip(ipaddress.ip_address("127.0.0.1")) is False
    assert is_allowed_ip(ipaddress.ip_address("127.0.0.1"), allow_loopback=True) is True
    assert is_allowed_ip(ipaddress.ip_address("10.0.0.1")) is False
    assert is_allowed_ip(ipaddress.ip_address("10.0.0.1"), allow_private=True) is True
    assert is_allowed_ip(ipaddress.ip_address("169.254.169.254")) is False
    assert is_allowed_ip(ipaddress.ip_address("169.254.169.254"), allow_private=True, allow_loopback=True) is False
    assert is_allowed_ip(ipaddress.ip_address("100.64.0.1")) is False
    assert is_allowed_ip(ipaddress.ip_address("100.64.0.1"), allow_private=True) is False
    mapped = normalize_ip("::ffff:169.254.169.254")
    assert is_allowed_ip(mapped, allow_private=True, allow_loopback=True) is False


def test_resolve_host_rejects_loopback_and_metadata(monkeypatch):
    def fake_addrinfo(host, port, type=0):
        if host in {"127.0.0.1", "localhost"}:
            return [_info("127.0.0.1", port)]
        if host == "169.254.169.254":
            return [_info("169.254.169.254", port)]
        raise AssertionError(host)

    monkeypatch.setattr(public_http.socket, "getaddrinfo", fake_addrinfo)
    with pytest.raises(UnsafeURL):
        resolve_host("127.0.0.1", 443)
    with pytest.raises(UnsafeURL):
        resolve_host("169.254.169.254", 80)
    # Loopback is allowed only when opted in.
    infos = resolve_host("127.0.0.1", 443, allow_loopback=True)
    assert infos[0][4][0] == "127.0.0.1"


def test_resolve_host_rejects_mixed_public_and_private(monkeypatch):
    def fake_addrinfo(host, port, type=0):
        return [_info("8.8.8.8", port), _info("10.1.2.3", port)]

    monkeypatch.setattr(public_http.socket, "getaddrinfo", fake_addrinfo)
    with pytest.raises(UnsafeURL):
        resolve_host("mixed.example", 443)


def test_plain_http_only_to_loopback(monkeypatch):
    def fake_addrinfo(host, port, type=0):
        if host == "127.0.0.1":
            return [_info("127.0.0.1", port)]
        return [_info("8.8.8.8", port)]

    monkeypatch.setattr(public_http.socket, "getaddrinfo", fake_addrinfo)
    resolve_url("http://127.0.0.1/agent", allow_loopback=True)
    with pytest.raises(UnsafeURL, match="HTTPS"):
        resolve_url("http://example.com/x", https_only=True)
    with pytest.raises(UnsafeURL, match="loopback"):
        resolve_url("http://example.com/x", allow_loopback=False)


def test_public_to_private_redirect_is_refused(monkeypatch):
    hops: list[str] = []

    class FakeResp:
        def __init__(self, status, location=None):
            self.status = status
            self._location = location

        def getheader(self, name):
            return self._location if name == "Location" else None

        def read(self, _n):
            return b""

    class FakeConn:
        def __init__(self, url):
            self.url = url

        def request(self, *a, **k):
            hops.append(self.url)

        def getresponse(self):
            if urlsplit(self.url).hostname == "public.example":
                return FakeResp(302, "https://127.0.0.1/secret")
            return FakeResp(200)

        def close(self):
            return None

    def fake_resolve(url, **kwargs):
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host in {"127.0.0.1", "localhost"}:
            raise UnsafeURL("refusing a non-allowed destination address")
        scheme, host, port, path, query = split_url(url)
        return scheme, host, port, path, query, [_info("8.8.8.8", port)]

    def fake_connection(scheme, host, port, infos, timeout):
        return FakeConn(f"{scheme}://{host}{'' if port in (80, 443) else ':' + str(port)}")

    monkeypatch.setattr(public_http, "resolve_url", fake_resolve)
    monkeypatch.setattr(public_http, "_connection", fake_connection)
    with pytest.raises(UnsafeURL):
        public_http.request("https://public.example/file", method="GET", max_redirects=3)
    assert hops == ["https://public.example"]


def test_post_does_not_follow_redirects(monkeypatch):
    class FakeResp:
        status = 302

        def getheader(self, name):
            return "https://example.com/next"

        def read(self, _n):
            return b""

    class FakeConn:
        def request(self, *a, **k):
            return None

        def getresponse(self):
            return FakeResp()

        def close(self):
            return None

    monkeypatch.setattr(
        public_http,
        "resolve_url",
        lambda url, **k: ("https", "example.com", 443, "/", "", [_info("8.8.8.8")]),
    )
    monkeypatch.setattr(public_http, "_connection", lambda *a, **k: FakeConn())
    with pytest.raises(UnsafeURL, match="redirect"):
        public_http.request("https://example.com/x", method="POST", max_redirects=0)
