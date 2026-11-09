"""Plugin data directory and path confinement.

State lives under the Hermes plugin data dir, overridable with TEMPLEOS_HOME.
Every host path used by tools or the pane is resolved (including symlinks)
and must stay inside that root. The root itself must not be a filesystem root.
"""

from __future__ import annotations

import os
from pathlib import Path

from templeos import PLUGIN_ID

ENV_HOME = "TEMPLEOS_HOME"

ISO_DIR = "isos"
DISK_DIR = "disks"
SOCKET_DIR = "sockets"
FRAME_DIR = "frames"

QMP_SOCK = "qmp.sock"
VNC_SOCK = "vnc.sock"
COM1_SOCK = "com1.sock"


class PathError(ValueError):
    """A path escaped the plugin data dir, was empty, or was a filesystem root."""

    def __init__(self, message: str, *, code: str = "path_escape") -> None:
        super().__init__(message)
        self.code = code


def _data_home_fallback() -> Path:
    """Profile-neutral fallback when Hermes APIs are unavailable.

    Does not read HERMES_HOME and does not hardcode ~/.hermes.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg and str(xdg).strip():
        return Path(xdg).expanduser() / "hermes-plugins" / PLUGIN_ID
    return Path.home() / ".local" / "share" / "hermes-plugins" / PLUGIN_ID


def _hermes_plugin_data_dir() -> Path | None:
    """Ask the host for a profile-aware plugin data dir when the API exists."""
    try:
        from hermes_cli.plugins import plugin_data_dir  # type: ignore
    except Exception:
        plugin_data_dir = None
    if callable(plugin_data_dir):
        try:
            path = plugin_data_dir(PLUGIN_ID)
        except TypeError:
            try:
                path = plugin_data_dir()
            except Exception:
                return None
        except Exception:
            return None
        if path:
            return Path(path)
    try:
        from hermes_constants import get_hermes_home  # type: ignore
    except Exception:
        return None
    try:
        home = get_hermes_home()
    except Exception:
        return None
    if home:
        return Path(home) / "plugin-data" / PLUGIN_ID
    return None


def home() -> Path:
    """Resolved plugin data root (TEMPLEOS_HOME wins)."""
    raw = os.environ.get(ENV_HOME)
    if raw and str(raw).strip():
        path = Path(raw).expanduser()
    else:
        path = _hermes_plugin_data_dir() or _data_home_fallback()
    resolved = path.expanduser().resolve()
    if resolved == resolved.anchor or resolved == Path(resolved.anchor).resolve():
        raise PathError(
            f"{ENV_HOME} must not be a filesystem root ({resolved}). "
            "Choose a directory under your home or plugin data folder.",
            code="path_escape",
        )
    return resolved


def ensure_layout(root: Path | None = None) -> Path:
    """Create the standard subdirs under the data root and return the root."""
    root = Path(root).resolve() if root is not None else home()
    for name in (ISO_DIR, DISK_DIR, SOCKET_DIR, FRAME_DIR):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def confine(path: str | os.PathLike[str] | Path, root: Path | None = None, label: str = "path") -> Path:
    """Resolve ``path`` (follow symlinks) and refuse anything outside ``root``."""
    root = (Path(root).expanduser().resolve() if root is not None else home())
    if not str(path).strip():
        raise PathError(
            f"{label} is empty. Choose a path inside {root}.",
            code="path_escape",
        )
    resolved = Path(path).expanduser().resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PathError(
            f"{label} must stay inside {root}. "
            f"{path} resolves to {resolved}, which is outside that folder.",
            code="path_escape",
        ) from exc
    return resolved


def isos_dir(root: Path | None = None) -> Path:
    return (root or home()) / ISO_DIR


def disks_dir(root: Path | None = None) -> Path:
    return (root or home()) / DISK_DIR


def sockets_dir(root: Path | None = None) -> Path:
    return (root or home()) / SOCKET_DIR


def frames_dir(root: Path | None = None) -> Path:
    return (root or home()) / FRAME_DIR


def socket_paths(root: Path | None = None) -> dict[str, Path]:
    base = sockets_dir(root)
    return {
        "qmp": base / QMP_SOCK,
        "vnc": base / VNC_SOCK,
        "com1": base / COM1_SOCK,
    }
