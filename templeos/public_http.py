"""Outbound address checks and connection-pinned HTTP(S).

Resolve every A/AAAA address, refuse destinations that are not allowed,
and pin the TCP connection to that result so a second DNS lookup cannot
rebind the host. Ambient proxies are disabled. URL credentials and control
characters are refused. Redirects, when allowed, are re-validated and
re-pinned at every hop.

ISO fetches use public HTTPS only (allow_loopback=False, allow_private=False).
Host-configured BBS and chat-bridge endpoints may opt into loopback or
private LAN addresses; they still refuse link-local, metadata, CGNAT,
multicast, reserved, and unspecified addresses.
"""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit

# CGNAT is not ipaddress.is_private on every Python; is_global is False.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_METADATA_V4 = ipaddress.ip_address("169.254.169.254")


class UnsafeURL(ValueError):
    """The URL or resolved address is not allowed."""


def normalize_ip(raw: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    ip = ipaddress.ip_address(raw)  # type: ignore[arg-type]
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def is_allowed_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
) -> bool:
    """Return True iff ``ip`` may be contacted under the given policy."""
    if ip == _METADATA_V4 or ip.is_unspecified or ip.is_multicast or ip.is_reserved or ip.is_link_local:
        return False
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        return False
    if ip.is_loopback:
        return allow_loopback
    if ip.is_private:
        return allow_private
    return bool(ip.is_global)


def resolve_host(
    host: str,
    port: int,
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
) -> list[tuple]:
    """Resolve ``host`` and return getaddrinfo results, all of which must be allowed."""
    if not host or any(ord(ch) < 32 or ch.isspace() for ch in host) or "%" in host:
        raise UnsafeURL("refusing a malformed host")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL("could not resolve host") from exc
    if not infos:
        raise UnsafeURL("could not resolve host")
    for info in infos:
        ip = normalize_ip(info[4][0])
        if not is_allowed_ip(ip, allow_loopback=allow_loopback, allow_private=allow_private):
            raise UnsafeURL("refusing a non-allowed destination address")
    return infos


def connect_pinned(
    infos: Iterable[tuple],
    *,
    timeout: float,
) -> socket.socket:
    """Connect to a previously vetted getaddrinfo result. No second DNS lookup."""
    last: OSError | None = None
    for family, kind, proto, _canon, addr in infos:
        sock = socket.socket(family, kind, proto)
        try:
            sock.settimeout(timeout)
            sock.connect(addr)
            return sock
        except OSError as exc:
            last = exc
            sock.close()
    raise last or OSError("no vetted destination was reachable")


def split_url(url: str) -> tuple[str, str, int, str, str]:
    """Return (scheme, host, port, path, query) after rejecting credentials and junk."""
    if not url or any(ord(ch) < 32 and ch not in "\t" for ch in url):
        raise UnsafeURL("refusing a malformed URL")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise UnsafeURL("only http or https URLs are allowed")
    if parts.username is not None or parts.password is not None:
        raise UnsafeURL("refusing URL credentials")
    host = parts.hostname
    if not host:
        raise UnsafeURL("URL has no host")
    if any(ord(ch) < 32 or ch.isspace() for ch in host) or "%" in host:
        raise UnsafeURL("refusing a malformed host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeURL("URL has an invalid port") from exc
    path = parts.path or "/"
    return parts.scheme, host, int(port), path, parts.query


def resolve_url(
    url: str,
    *,
    allow_loopback: bool = False,
    allow_private: bool = False,
    https_only: bool = False,
) -> tuple[str, str, int, str, str, list[tuple]]:
    scheme, host, port, path, query = split_url(url)
    if https_only and scheme != "https":
        raise UnsafeURL("HTTPS is required")
    if scheme == "http":
        # Plain HTTP is only for explicit loopback development, never LAN or public.
        infos = resolve_host(host, port, allow_loopback=True, allow_private=False)
        for info in infos:
            if not normalize_ip(info[4][0]).is_loopback:
                raise UnsafeURL("plain HTTP is only allowed to loopback")
        if not allow_loopback:
            raise UnsafeURL("plain HTTP is only allowed to loopback")
        return scheme, host, port, path, query, infos
    infos = resolve_host(
        host, port, allow_loopback=allow_loopback, allow_private=allow_private
    )
    return scheme, host, port, path, query, infos


def _connection(
    scheme: str,
    host: str,
    port: int,
    infos: list[tuple],
    timeout: float,
) -> http.client.HTTPConnection:
    cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    # Pass the hostname so TLS SNI and certificate verification stay on the name.
    conn = cls(host, port, timeout=timeout)
    conn._create_connection = lambda *a, **k: connect_pinned(infos, timeout=timeout)  # type: ignore[method-assign]
    return conn


def request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_redirects: int = 0,
    allow_loopback: bool = False,
    allow_private: bool = False,
    https_only: bool = False,
    max_bytes: int | None = None,
    dest: Path | None = None,
    sha256: hashlib._Hash | None = None,
) -> tuple[int, bytes]:
    """Perform a connection-pinned request. POST should pass max_redirects=0.

    When ``dest`` is set, the body is streamed to that path (and optionally
    hashed) instead of being returned, and the second result is b\"\".
    """
    method = method.upper()
    current = url
    hdrs = dict(headers or {})
    for hop in range(max_redirects + 1):
        scheme, host, port, path, query, infos = resolve_url(
            current,
            allow_loopback=allow_loopback,
            allow_private=allow_private,
            https_only=https_only,
        )
        target = path + (("?" + query) if query else "")
        conn = _connection(scheme, host, port, infos, timeout)
        try:
            conn.request(method, target, body=body, headers=hdrs)
            response = conn.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                if method == "POST" or max_redirects <= 0:
                    raise UnsafeURL("refusing to follow a redirect")
                location = response.getheader("Location")
                if not location or hop >= max_redirects:
                    raise UnsafeURL("redirect limit or missing destination")
                current = urljoin(current, location)
                if method == "GET" and response.status in {301, 302, 303}:
                    body = None
                continue
            return response.status, _read_body(response, max_bytes=max_bytes, dest=dest, sha256=sha256)
        finally:
            conn.close()
    raise UnsafeURL("redirect limit exceeded")


def _read_body(
    response: http.client.HTTPResponse,
    *,
    max_bytes: int | None,
    dest: Path | None,
    sha256: hashlib._Hash | None,
) -> bytes:
    written = 0
    chunks: list[bytes] = []
    handle = dest.open("wb") if dest is not None else None
    try:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if max_bytes is not None and written > max_bytes:
                raise UnsafeURL("response exceeded the size bound")
            if sha256 is not None:
                sha256.update(chunk)
            if handle is not None:
                handle.write(chunk)
            else:
                chunks.append(chunk)
    finally:
        if handle is not None:
            handle.close()
    return b"" if dest is not None else b"".join(chunks)


def download_https(
    url: str,
    dest: Path,
    *,
    expected_sha256: str,
    expected_bytes: int | None = None,
    timeout: float = 60.0,
    max_redirects: int = 5,
    headers: dict[str, str] | None = None,
) -> Path:
    """Stream a public HTTPS URL to ``dest`` and require the pinned SHA-256."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    limit = None
    if expected_bytes:
        limit = int(expected_bytes) + max(1024 * 1024, int(expected_bytes) * 5 // 100)
    digest = hashlib.sha256()
    try:
        status, _ = request(
            url,
            method="GET",
            headers=headers or {},
            timeout=timeout,
            max_redirects=max_redirects,
            allow_loopback=False,
            allow_private=False,
            https_only=True,
            max_bytes=limit,
            dest=dest,
            sha256=digest,
        )
    except (UnsafeURL, OSError, ssl.SSLError, TimeoutError, ValueError, http.client.HTTPException):
        dest.unlink(missing_ok=True)
        raise
    if status != 200:
        dest.unlink(missing_ok=True)
        raise UnsafeURL("official download did not return HTTP 200")
    if digest.hexdigest() != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise OSError("downloaded ISO failed the pinned SHA-256 check")
    return dest
