"""Persisted plugin settings (preferred guest flavor) under the data dir."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from templeos.flavors import DEFAULT, FLAVOR_IDS, FlavorError, get_flavor
from templeos.paths import home, isos_dir

SETTINGS_NAME = "settings.json"
ENV_FLAVOR = "TEMPLEOS_FLAVOR"
_MODE = 0o600


def _path() -> Path:
    return home() / SETTINGS_NAME


def load_preferred() -> str:
    """Return the saved (or env-overridden) flavor id, else the default."""
    raw = (os.environ.get(ENV_FLAVOR) or "").strip()
    if raw:
        try:
            return get_flavor(raw)["id"]
        except FlavorError:
            pass
    path = _path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            data = None
        if isinstance(data, dict) and data.get("flavor"):
            try:
                return get_flavor(str(data["flavor"]))["id"]
            except FlavorError:
                pass
    return DEFAULT


def save_preferred(flavor_id: str) -> dict[str, Any]:
    """Persist a valid flavor id to settings.json (mode 0600)."""
    rec = get_flavor(flavor_id)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError, UnicodeError):
            existing = {}
    existing["flavor"] = rec["id"]
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(_MODE)
    except OSError:
        pass
    return rec


def iso_state(flavor_id: str | None = None) -> dict[str, Any]:
    """Inspect the cached ISO for one flavor. Never fetches."""
    rec = get_flavor(flavor_id or load_preferred())
    dest = isos_dir() / str(rec["iso_filename"])
    expected = str(rec["sha256"]).lower()
    present = dest.is_file()
    digest = None
    size = None
    if present:
        size = dest.stat().st_size
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        sha_state = "verified" if digest == expected else "mismatch"
        sha_ok = digest == expected
    else:
        sha_state = "missing"
        sha_ok = False
    return {
        "id": rec["id"],
        "name": rec["name"],
        "default": bool(rec.get("default")),
        "url": rec["url"],
        "sha256": expected,
        "bytes": int(rec["bytes"]),
        "iso_filename": rec["iso_filename"],
        "present": present,
        "sha_ok": sha_ok,
        "sha_state": sha_state,
        "digest": digest,
        "size": size,
    }


def list_iso_states() -> list[dict[str, Any]]:
    return [iso_state(fid) for fid in FLAVOR_IDS]


def flavor_status() -> dict[str, Any]:
    """Secret-free flavor picker payload for tools, /status, and /settings."""
    preferred = load_preferred()
    rec = get_flavor(preferred)
    selected = iso_state(preferred)
    running = False
    current = None
    try:
        from templeos.vm import status as vm_status

        body = vm_status()
        running = bool(body.get("running"))
        current = body.get("flavor")
    except Exception:
        pass
    pending = bool(running and current and current != preferred)
    notice = None
    if pending:
        current_name = current
        try:
            current_name = get_flavor(str(current))["name"]
        except FlavorError:
            pass
        notice = (
            f"{rec['name']} is selected and will apply on the next boot. "
            f"The running guest is still {current_name}. "
            "Stop and start to switch now."
        )
    return {
        "ok": True,
        "flavor": preferred,
        "flavor_name": rec["name"],
        "preferred_flavor": preferred,
        "current_flavor": current,
        "running": running,
        "apply_on_next_boot": pending,
        "notice": notice,
        "sha_state": selected["sha_state"],
        "sha256": selected["sha256"],
        "iso": selected,
        "flavors": list_iso_states(),
    }


def apply_flavor_choice(flavor_id: str, *, fetch: bool = True) -> dict[str, Any]:
    """Save the flavor, fetch/verify the pinned ISO if needed, and describe apply state."""
    rec = save_preferred(flavor_id)
    from templeos.doctor import ensure_iso

    iso = ensure_iso(rec["id"], fetch=fetch)
    status = flavor_status()
    status["iso_fetch"] = {
        "ok": bool(iso.get("ok")),
        "fetched": bool(iso.get("fetched")),
        "code": iso.get("code"),
        "error": iso.get("error"),
        "sha256": iso.get("sha256") or iso.get("expected"),
        "path": iso.get("path"),
    }
    if iso.get("ok") is False:
        status["ok"] = False
        status["error"] = iso.get("error") or f"Could not prepare {rec['name']}."
        status["code"] = iso.get("code") or "iso_missing"
        status["fix"] = iso.get("fix") or "Retry the official pinned download, then start the guest."
        if not status.get("notice"):
            status["notice"] = status["error"]
        return status
    if status.get("apply_on_next_boot"):
        pass
    elif iso.get("fetched"):
        status["notice"] = (
            f"Downloaded and SHA-256-verified {rec['name']}. Start the guest to boot it."
        )
    else:
        status["notice"] = f"{rec['name']} is pinned and SHA-256 verified. Start the guest to boot it."
    return status


def apply_config(ctx: Any) -> str | None:
    """Honor a plugin config/settings ``flavor`` value at register time."""
    if ctx is None:
        return None
    raw = None
    for attr in ("config", "settings", "plugin_config"):
        try:
            value = getattr(ctx, attr, None)
        except Exception:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, dict):
            if "flavor" in value:
                raw = value.get("flavor")
                break
            nested = value.get("templeos")
            if isinstance(nested, dict) and "flavor" in nested:
                raw = nested.get("flavor")
                break
    if raw is None:
        for meth in ("get_config", "config_get"):
            fn = getattr(ctx, meth, None)
            if not callable(fn):
                continue
            for key in ("flavor", "templeos.flavor"):
                try:
                    value = fn(key)
                except Exception:
                    continue
                if value is not None:
                    raw = value
                    break
            if raw is not None:
                break
    if raw is None:
        return None
    try:
        rec = save_preferred(str(raw))
    except FlavorError:
        return None
    return rec["id"]
