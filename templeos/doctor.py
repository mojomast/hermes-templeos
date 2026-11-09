"""Host doctor: QEMU binary, KVM usability, pinned ISOs, disk, sockets.

kvm is usable only when /dev/kvm can actually be opened, not merely when
the node exists. Do not install packages or write udev rules; tell the user
the apt or brew command. Fetch ISOs only from official URLs in flavors.py
and verify the pinned SHA-256 (delete partials on mismatch).
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from templeos.envsafe import child_env
from templeos.flavors import DEFAULT, FlavorError, get_flavor, iso_filename
from templeos.paths import disks_dir, ensure_layout, home, isos_dir, socket_paths
from templeos.qemu import find_binary, QEMU_BINARY, QEMU_IMG

KVM_NODE = "/dev/kvm"
_SHA256_LEN = 64
_HASH_CHUNK = 1024 * 1024
_REDIRECT_HOPS = 5
_FETCH_TIMEOUT_S = 120.0


def kvm_usable() -> bool:
    """True only if /dev/kvm can be opened read/write. Existence is not enough."""
    return kvm_openable(KVM_NODE)


def kvm_openable(node: str | Path) -> bool:
    """Open ``node`` read/write and close it. Used by tests with a stand-in file."""
    try:
        fd = os.open(str(node), os.O_RDWR)
    except OSError:
        return False
    try:
        os.close(fd)
    except OSError:
        pass
    return True


def qemu_version() -> dict[str, Any]:
    """Locate qemu-system-x86_64 on PATH and return {path, version}."""
    path = find_binary(QEMU_BINARY)
    if path is None:
        return {
            "ok": False,
            "path": None,
            "version": None,
            "code": "qemu_missing",
            "error": "qemu-system-x86_64 was not found on PATH.",
            "fix": _qemu_install_fix(),
        }
    try:
        completed = subprocess.run(
            [str(path), "--version"],
            env=child_env(),
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "path": str(path),
            "version": None,
            "code": "qemu_missing",
            "error": f"qemu-system-x86_64 --version failed: {exc}",
            "fix": _qemu_install_fix(),
        }
    text = (completed.stdout or completed.stderr or b"").decode("utf-8", "replace")
    version = _parse_qemu_version(text)
    return {
        "ok": completed.returncode == 0,
        "path": str(path),
        "version": version,
        "output": text.strip().splitlines()[0] if text.strip() else "",
        "code": None if completed.returncode == 0 else "qemu_missing",
    }


def ensure_iso(flavor: str = "tinkeros", *, fetch: bool = True) -> dict[str, Any]:
    """Fetch the pinned ISO if missing, verify SHA-256, refuse a hash mismatch.

    ``fetch=False`` only inspects the cache (used by doctor checks so CI never
    downloads). When fetch is true, the ISO is downloaded only from the
    official HTTPS URL in flavors.py.
    """
    rec = get_flavor(flavor)
    ensure_layout()
    dest = isos_dir() / str(rec["iso_filename"])
    expected = str(rec["sha256"]).lower()
    official = str(rec["url"])
    if dest.exists():
        digest = sha256_file(dest)
        if digest == expected:
            return {
                "ok": True,
                "path": str(dest),
                "sha256": digest,
                "fetched": False,
                "flavor": rec["id"],
                "bytes": dest.stat().st_size,
            }
        dest.unlink()
        _unlink_partials(dest)
        if not fetch:
            return {
                "ok": False,
                "path": str(dest),
                "sha256": digest,
                "expected": expected,
                "fetched": False,
                "flavor": rec["id"],
                "code": "iso_hash_mismatch",
                "error": f"Cached ISO for {rec['id']} failed the pinned SHA-256 check and was deleted.",
                "fix": "Run doctor setup (ensure_iso) to re-fetch the official pin.",
            }
    if not dest.exists() and not fetch:
        return {
            "ok": False,
            "path": str(dest),
            "sha256": None,
            "fetched": False,
            "flavor": rec["id"],
            "code": "iso_missing",
            "error": f"Pinned ISO {rec['iso_filename']} is not in the cache.",
            "fix": "Run templeos_vm op=doctor with setup, or copy the official ISO into the isos cache.",
        }
    if official != str(get_flavor(flavor)["url"]):
        # Defensive: never fetch a URL that is not the live pin.
        return {
            "ok": False,
            "code": "iso_missing",
            "error": "Refusing to fetch a URL that is not the official flavor pin.",
            "fix": "Use the URL recorded in templeos.flavors.",
            "flavor": rec["id"],
        }
    partial = dest.with_name(dest.name + ".partial")
    try:
        download_official(official, partial, expected_sha256=expected, expected_bytes=rec.get("bytes"))
        digest = sha256_file(partial)
        if digest != expected:
            partial.unlink(missing_ok=True)
            return {
                "ok": False,
                "path": str(dest),
                "sha256": digest,
                "expected": expected,
                "fetched": True,
                "flavor": rec["id"],
                "code": "iso_hash_mismatch",
                "error": f"Fetched ISO for {rec['id']} failed the pinned SHA-256 check; the partial was deleted.",
                "fix": "Delete any remaining partial and run doctor setup again.",
            }
        partial.replace(dest)
        return {
            "ok": True,
            "path": str(dest),
            "sha256": digest,
            "fetched": True,
            "flavor": rec["id"],
            "bytes": dest.stat().st_size,
        }
    except Exception as exc:
        _unlink_partials(dest)
        return {
            "ok": False,
            "path": str(dest),
            "fetched": False,
            "flavor": rec["id"],
            "code": "iso_missing",
            "error": f"Failed to fetch the official ISO: {exc}",
            "fix": "Check network access to the official URL, then retry doctor setup.",
        }


def doctor(*, setup: bool = False, flavor: str = DEFAULT) -> dict[str, Any]:
    """Full doctor report: qemu, kvm, iso, disk, sockets (existence only), ok, checks.

    ``setup=True`` downloads the pinned ISO for ``flavor`` from the official
    URL and verifies it. The default path never fetches (safe for CI).
    """
    try:
        rec = get_flavor(flavor)
    except FlavorError as exc:
        return {
            "ok": False,
            "code": "unknown_flavor",
            "error": str(exc),
            "fix": "Use flavor tinkeros, templeos, or zealos.",
            "checks": [],
        }
    root = ensure_layout()
    qemu = qemu_version()
    kvm_exists = Path(KVM_NODE).exists()
    kvm = kvm_usable()
    if kvm:
        kvm_note = f"{KVM_NODE} opened read/write; KVM acceleration is available."
    elif kvm_exists:
        kvm_note = (
            f"{KVM_NODE} exists but cannot be opened; falling back to TCG. "
            "This is not a doctor failure. Grant the user access to KVM "
            "(usually the kvm group) to enable hardware acceleration."
        )
    else:
        kvm_note = f"{KVM_NODE} is absent; falling back to TCG."

    iso = ensure_iso(rec["id"], fetch=bool(setup))
    disk = disks_dir(root) / f"{rec['id']}.qcow2"
    socks = {key: path.exists() for key, path in socket_paths(root).items()}
    img = find_binary(QEMU_IMG)

    checks = [
        _check("qemu", bool(qemu.get("ok")), qemu.get("output") or qemu.get("error") or str(qemu.get("path"))),
        _check("kvm", True, kvm_note),  # TCG fallback is a note, not a failure.
        _check(
            "iso",
            bool(iso.get("ok")),
            iso.get("error") or f"{iso_filename(rec['id'])} sha256 ok" if iso.get("ok") else "ISO not ready",
        ),
        _check(
            "disk",
            True,
            f"{disk} present" if disk.exists() else f"{disk} missing (will be created on start)",
        ),
        _check(
            "qemu-img",
            img is not None,
            str(img) if img is not None else "qemu-img was not found on PATH; needed to create the qcow2.",
        ),
        _check("sockets", True, "existence only: " + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in socks.items())),
    ]
    qemu_ok = bool(qemu.get("ok"))
    iso_ok = bool(iso.get("ok"))
    img_ok = img is not None
    ok = qemu_ok and iso_ok and img_ok
    code = None
    error = None
    fix = None
    if not qemu_ok:
        code = "qemu_missing"
        error = str(qemu.get("error") or "qemu-system-x86_64 is missing.")
        fix = _qemu_install_fix()
    elif not img_ok:
        code = "qemu_missing"
        error = "qemu-img was not found on PATH."
        fix = _qemu_install_fix()
    elif not iso_ok:
        code = str(iso.get("code") or "iso_missing")
        error = str(iso.get("error") or "Pinned ISO is not ready.")
        fix = str(iso.get("fix") or "Run doctor setup to fetch the official ISO.")
    if not ok:
        code = code or "doctor_failed"
        error = error or "Doctor checks failed."
        fix = fix or "Read the checks, install QEMU or fix ISO permissions, then retry."
    return {
        "ok": ok,
        "code": code,
        "error": error,
        "fix": fix,
        "flavor": rec["id"],
        "home": str(home()),
        "qemu": {k: qemu[k] for k in ("ok", "path", "version") if k in qemu},
        "kvm": {"usable": kvm, "exists": kvm_exists, "note": kvm_note},
        "iso": {k: iso[k] for k in iso if k not in {"fix"}},
        "disk": {"present": disk.exists(), "path": str(disk)},
        "sockets": socks,
        "accel_recommended": "kvm" if kvm else "tcg",
        "checks": checks,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_official(
    url: str,
    dest: Path,
    *,
    expected_sha256: str,
    expected_bytes: int | None = None,
) -> Path:
    """Stream ``url`` to ``dest`` after checking it is a public HTTPS official pin."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.unlink(missing_ok=True)
    _assert_public_https(url)
    timeout = _FETCH_TIMEOUT_S
    limit = None
    if expected_bytes:
        limit = int(expected_bytes) + max(1024 * 1024, int(expected_bytes) * 5 // 100)

    class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            hops = getattr(req, "_templeos_hops", 0) + 1
            if hops > _REDIRECT_HOPS:
                raise OSError("too many redirects while fetching the official ISO")
            _assert_public_https(newurl)
            nxt = urllib.request.HTTPRedirectHandler.redirect_request(
                self, req, fp, code, msg, headers, newurl
            )
            if nxt is not None:
                nxt._templeos_hops = hops  # type: ignore[attr-defined]
            return nxt

    opener = urllib.request.build_opener(_HttpsRedirect)
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "hermes-templeos/0.1"})
    digest = hashlib.sha256()
    written = 0
    try:
        with opener.open(request, timeout=timeout) as resp, dest.open("wb") as handle:
            final = resp.geturl() if hasattr(resp, "geturl") else url
            _assert_public_https(final)
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if limit is not None and written > limit:
                    raise OSError("ISO download exceeded the expected size bound")
                digest.update(chunk)
                handle.write(chunk)
    except (urllib.error.URLError, OSError, TimeoutError, ValueError, socket.timeout):
        dest.unlink(missing_ok=True)
        raise
    got = digest.hexdigest()
    if got != expected_sha256.lower():
        dest.unlink(missing_ok=True)
        raise OSError("downloaded ISO failed the pinned SHA-256 check")
    return dest


def _assert_public_https(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise OSError("ISO fetch requires HTTPS")
    if parsed.username or parsed.password or parsed.params:
        raise OSError("refusing ISO URL credentials")
    host = parsed.hostname
    if not host or "\x00" in url or any(ord(ch) < 32 for ch in url if ch not in "\t"):
        raise OSError("refusing a malformed ISO URL")
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OSError(f"could not resolve official ISO host {host}") from exc
    if not infos:
        raise OSError(f"could not resolve official ISO host {host}")
    for info in infos:
        raw = info[4][0]
        ip = ipaddress.ip_address(raw)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_unspecified or ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise OSError("refusing to fetch an ISO from a non-public address")


def _parse_qemu_version(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if "version" in line.lower():
            parts = line.replace("(", " ").split()
            for idx, part in enumerate(parts):
                if part.lower() == "version" and idx + 1 < len(parts):
                    return parts[idx + 1]
            return line
    return text.strip().splitlines()[0] if text.strip() else None


def _qemu_install_fix() -> str:
    return (
        "Install qemu-system-x86_64 and qemu-img with your package manager "
        "(apt install qemu-system-x86 qemu-utils, or brew install qemu). "
        "The plugin does not install packages or write udev rules."
    )


def _check(ident: str, ok: bool, detail: str | None) -> dict[str, Any]:
    return {"id": ident, "ok": bool(ok), "detail": detail or ""}


def _unlink_partials(dest: Path) -> None:
    dest.with_name(dest.name + ".partial").unlink(missing_ok=True)
    dest.with_suffix(dest.suffix + ".partial").unlink(missing_ok=True)
