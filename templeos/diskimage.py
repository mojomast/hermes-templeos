"""Optional preinstalled Temple of Hermes disk image (local storage for C:).

The disk is an *option* for the default ``templeoh`` flavor. Temple of Hermes
remains the default guest; the live ISO + scratch qcow2 path is unchanged when
this option is off or the image cannot be downloaded or verified.

The pinned image is never modified: when enabled, QEMU boots a per-user
copy-on-write qcow2 overlay under the plugin data dir whose backing file is the
verified base image. The base is fetched once from the official GitHub
release asset (public HTTPS, connection-pinned, no proxy) into the plugin data
dir and must match the pinned size and SHA-256; any failure falls back to the
live ISO.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from templeos.envsafe import child_env
from templeos.flavors import DEFAULT, FlavorError, get_flavor
from templeos.paths import disks_dir, home
from templeos.qemu import QEMU_IMG, find_binary

SETTINGS_NAME = "settings.json"
ENV_DISK_IMAGE = "TEMPLEOS_DISK_IMAGE"
DISK_FLAVOR = "templeoh"
DISK_ID = "templeoh-disk"

# Pinned artifact facts from the temple-of-hermes hermes/disk-image-0.1.3
DISK_FILENAME = "TempleOfHermes-0.1.2-disk.qcow2"
DISK_SHA256 = "d41672fb148051f3b4d85d06895bfc0f67da0e3af539bf89bbf4933056241087"
DISK_BYTES = 11_082_240
# Official prerelease asset (mojomast/temple-of-hermes, tag disk-image-0.1.3-preview).
DISK_IMAGE_URL: str | None = (
    "https://github.com/mojomast/temple-of-hermes/releases/download/"
    "disk-image-0.1.3-preview/TempleOfHermes-0.1.2-disk.qcow2"
)
# Back-compat alias for older callers/tests.
FUTURE_DISK_IMAGE_URL: str | None = DISK_IMAGE_URL
DEFAULT_DISK_IMAGE = "on"

_MODE = 0o600
_HASH_CHUNK = 1024 * 1024

# Test seam: monkeypatch this (or diskimage.subprocess.run) in unit tests.
def _default_run(argv, **kwargs):
    return subprocess.run(argv, **kwargs)


run_command = _default_run


def record() -> dict[str, Any]:
    """Pinned disk-image facts (official release asset URL, size, SHA-256)."""
    return {
        "id": DISK_ID,
        "flavor": DISK_FLAVOR,
        "filename": DISK_FILENAME,
        "sha256": DISK_SHA256,
        "size": DISK_BYTES,
        "url": DISK_IMAGE_URL,
    }


def _settings_path() -> Path:
    return home() / SETTINGS_NAME


def _read_settings() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _on_off(value: Any) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    token = str(value or "").strip().lower()
    if token in {"on", "1", "true", "yes", "enabled"}:
        return "on"
    if token in {"off", "0", "false", "no", "disabled", ""}:
        return "off"
    raise ValueError('disk_image must be "on" or "off".')


def load_config() -> dict[str, Any]:
    """Persisted option plus the env override. Never touches the filesystem."""
    data = _read_settings()
    try:
        enabled = _on_off(data.get("disk_image", DEFAULT_DISK_IMAGE))
    except ValueError:
        enabled = DEFAULT_DISK_IMAGE
    path = str(data.get("disk_image_path") or "").strip()
    env_path = str(os.environ.get(ENV_DISK_IMAGE) or "").strip()
    return {
        "disk_image": enabled,
        "disk_image_path": path,
        "effective_path": env_path or path,
        "path_source": "env" if env_path else ("config" if path else None),
    }


def save_config(*, disk_image: Any = None, disk_image_path: Any = None) -> dict[str, Any]:
    """Persist the option in settings.json without disturbing other keys."""
    data = _read_settings()
    if disk_image is not None:
        data["disk_image"] = _on_off(disk_image)
    if disk_image_path is not None:
        data["disk_image_path"] = str(disk_image_path or "").strip()
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(_MODE)
    except OSError:
        pass
    return load_config()


def enabled() -> bool:
    return load_config()["disk_image"] == "on"


def configured_path() -> str:
    return str(load_config()["effective_path"] or "")


def cached_path(root: Path | None = None) -> Path:
    """Where the downloaded official base image lives (never modified)."""
    return disks_dir(root) / DISK_FILENAME


def _download(url: str, dest: Path) -> Path:
    from templeos.doctor import download_official

    return download_official(url, dest, expected_sha256=DISK_SHA256, expected_bytes=DISK_BYTES)


download_image = _download


def ensure_image(*, fetch: bool = True) -> dict[str, Any]:
    """Verify the configured or cached image; download the official pin if allowed.

    Never raises: a failed download or verification returns a structured
    status so callers fall back to the live ISO.
    """
    info = verify()
    if info["ok"] or info.get("path_set") or not fetch:
        return info
    rec = record()
    if not rec["url"]:
        return info
    dest = cached_path()
    try:
        download_image(str(rec["url"]), dest)
    except Exception as exc:  # network, TLS, size or SHA-256 failure
        dest.unlink(missing_ok=True)
        return {
            **info,
            "ok": False,
            "state": "download_failed",
            "code": "disk_image_download_failed",
            "message": f"Preinstalled disk download failed: {type(exc).__name__}.",
            "fix": "Check network access to github.com, or set disk_image off to boot the live ISO.",
        }
    return verify()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Verify a local image against the pinned size and SHA-256.

    Returns a structured status. A missing path is only an error when the
    option is enabled; callers use ``status`` for the friendlier view.
    """
    rec = record()
    raw = str(path or configured_path() or "").strip()
    from_cache = False
    if not raw and cached_path().is_file():
        raw = str(cached_path())
        from_cache = True
    base = {
        "id": rec["id"],
        "filename": rec["filename"],
        "expected_sha256": rec["sha256"],
        "expected_size": rec["size"],
        "url": rec["url"],
    }
    if not raw:
        if rec["url"]:
            return {
                **base,
                "ok": False,
                "state": "not_downloaded",
                "code": "disk_image_not_downloaded",
                "path": None,
                "sha256": None,
                "bytes": None,
                "path_set": False,
                "message": "The preinstalled disk image has not been downloaded yet.",
                "fix": "Run templeos_vm op=doctor setup or start the VM to fetch the pinned image.",
            }
        if rec["url"] is None:
            return {
                **base,
                "ok": False,
                "state": "unpublished",
                "code": "disk_image_unpublished",
                "path": None,
                "sha256": None,
                "bytes": None,
                "path_set": False,
                "message": (
                    "The preinstalled Temple of Hermes disk image is not published yet; "
                    "set disk_image_path to a downloaded copy, or keep booting the live ISO."
                ),
                "fix": "Download the disk image when it is released, verify it, then set disk_image_path.",
            }
        return {
            **base,
            "ok": False,
            "state": "missing",
            "code": "disk_image_missing",
            "path": None,
            "sha256": None,
            "bytes": None,
            "path_set": False,
            "message": "No local preinstalled disk image is configured.",
            "fix": "Set disk_image_path to the downloaded qcow2.",
        }
    image = Path(raw).expanduser()
    if not image.is_file():
        return {
            **base,
            "ok": False,
            "state": "missing",
            "code": "disk_image_missing",
            "path": str(image),
            "sha256": None,
            "bytes": None,
            "path_set": not from_cache,
            "message": "The configured preinstalled disk image is missing.",
            "fix": "Download the pinned image and point disk_image_path at it.",
        }
    size = image.stat().st_size
    if size != int(rec["size"]):
        return {
            **base,
            "ok": False,
            "state": "unverified",
            "code": "disk_image_size_mismatch",
            "path": str(image),
            "sha256": None,
            "bytes": size,
            "path_set": not from_cache,
            "message": (
                f"Disk image size {size} does not match the pinned {rec['size']} bytes."
            ),
            "fix": "Use the exact pinned qcow2; do not resize or repack it.",
        }
    digest = sha256_file(image)
    if digest != str(rec["sha256"]).lower():
        return {
            **base,
            "ok": False,
            "state": "unverified",
            "code": "disk_image_hash_mismatch",
            "path": str(image),
            "sha256": digest,
            "bytes": size,
            "path_set": not from_cache,
            "message": "Disk image SHA-256 does not match the pinned hash.",
            "fix": "Replace the file with the official pinned download.",
        }
    return {
        **base,
        "ok": True,
        "state": "ok",
        "code": None,
        "path": str(image),
        "sha256": digest,
        "bytes": size,
        "path_set": not from_cache,
        "message": "Preinstalled disk image verified.",
        "fix": None,
    }


def status() -> dict[str, Any]:
    """Public, secret-free option status for doctor, /status and the pane."""
    rec = record()
    cfg = load_config()
    info = verify(cfg["effective_path"])
    state = info["state"]
    if not cfg["disk_image"] == "on":
        if state == "ok":
            text = "Off; verified disk image available. Temple of Hermes boots the live ISO."
        elif state == "unpublished":
            text = "Off; preinstalled disk is not published yet. Temple of Hermes boots the live ISO."
        elif state in ("not_downloaded", "download_failed"):
            text = "Off; Temple of Hermes boots the live ISO. Turn on to download the preinstalled disk."
        elif state == "missing":
            text = "Off; disk_image_path is set but the image is missing."
        else:
            text = "Off; disk image is unverified (size or SHA-256 mismatch)."
    elif state == "ok":
        text = "Verified; local storage (C:) boots from a copy-on-write overlay."
    elif state == "unpublished":
        text = "Not published yet; set disk_image_path to a verified image."
    elif state == "not_downloaded":
        text = "On; the official disk image downloads and verifies on the next start (live ISO until then)."
    elif state == "download_failed":
        text = "Download or verification failed; booting the live ISO instead."
    elif state == "missing":
        text = "disk_image_path is set but the image is missing."
    else:
        text = "Disk image is unverified (size or SHA-256 mismatch)."
    return {
        **rec,
        "default_flavor": DEFAULT,
        "enabled": cfg["disk_image"] == "on",
        "verified": bool(info.get("ok")),
        "state": state,
        "code": info.get("code"),
        "path": info.get("path"),
        "path_set": bool(info.get("path_set")),
        "path_source": cfg.get("path_source"),
        "sha256": info.get("sha256"),
        "bytes": info.get("bytes"),
        "message": info.get("message"),
        "fix": info.get("fix"),
        "text": text,
    }


def overlay_path(root: Path | None = None) -> Path:
    """Per-user overlay under the plugin data dir; the pinned base is read-only."""
    return disks_dir(root) / f"{DISK_ID}-overlay.qcow2"


def ensure_overlay(
    base: str | os.PathLike[str],
    overlay: str | os.PathLike[str] | None = None,
    *,
    replace: bool = False,
) -> Path:
    """Create (or reuse) a qcow2 overlay backed by the verified base image."""
    base_path = Path(base).expanduser()
    dest = Path(overlay).expanduser() if overlay is not None else overlay_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not replace:
        return dest
    if dest.exists():
        try:
            dest.unlink()
        except OSError:
            pass
    binary = find_binary(QEMU_IMG)
    exe = str(binary) if binary is not None else QEMU_IMG
    argv = [
        exe,
        "create",
        "-f",
        "qcow2",
        "-b",
        str(base_path),
        "-F",
        "qcow2",
        str(dest),
    ]
    completed = run_command(
        argv,
        env=child_env(),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0 or not dest.exists():
        dest.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"{QEMU_IMG} create overlay failed for {dest}")
    return dest


def resolve(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Alias for :func:`verify`; resolves the configured or supplied image."""
    return verify(path)


resolve_image = resolve
pinned_record = record


def create_overlay(
    base: str | os.PathLike[str],
    overlay: str | os.PathLike[str] | None = None,
    *,
    replace: bool = False,
) -> Path:
    """Alias for :func:`ensure_overlay` (copy-on-write over the pinned base)."""
    return ensure_overlay(base, overlay, replace=replace)


def boot_plan(flavor_id: str | None = None, *, fetch: bool = True) -> dict[str, Any]:
    """Decide whether to boot the disk overlay or the normal live ISO.

    Returns ``mode="disk"`` only for the default Temple of Hermes flavor when the
    option is on and the local image verifies. Otherwise ``mode="iso"`` keeps the
    existing boot path; an unpublished image is a status, never a boot failure.
    """
    try:
        rec = get_flavor(flavor_id or DEFAULT)
    except FlavorError:
        rec = get_flavor(DEFAULT)
    info = status()
    if rec["id"] != DISK_FLAVOR:
        return {
            "mode": "iso",
            "enabled": info["enabled"],
            "reason": "flavor_not_templeoh",
            "status": info,
        }
    if not info["enabled"]:
        return {"mode": "iso", "enabled": False, "reason": "option_off", "status": info}
    if not info["verified"] and fetch and not info.get("path_set"):
        fetched = ensure_image(fetch=True)
        info = status()
        if not fetched.get("ok") and fetched.get("state") == "download_failed":
            info = {**info, "verified": False, "state": "download_failed",
                    "code": fetched.get("code"), "text": "Download or verification failed; booting the live ISO instead."}
    if not info["verified"]:
        return {
            "mode": "iso",
            "enabled": True,
            "fallback": True,
            "reason": info["state"],
            "notice": info["text"],
            "status": info,
        }
    return {
        "mode": "disk",
        "enabled": True,
        "reason": "verified",
        "base": Path(str(info["path"])),
        "overlay": overlay_path(),
        "status": info,
    }
