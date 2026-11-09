from __future__ import annotations

import pytest

from templeos.paths import PathError, confine, ensure_layout, home, socket_paths


def test_home_uses_templeos_home(tos_home):
    assert home() == tos_home.resolve()
    root = ensure_layout()
    assert (root / "isos").is_dir()
    assert (root / "disks").is_dir()
    socks = socket_paths()
    assert socks["qmp"].name == "qmp.sock"
    assert socks["vnc"].parent == root / "sockets"


def test_confine_rejects_escape_and_symlink(tos_home, tmp_path):
    inside = tos_home / "disks" / "guest.qcow2"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(b"x")
    assert confine(inside, tos_home, "disk") == inside.resolve()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(PathError, match="must stay inside"):
        confine(outside, tos_home, "disk")
    with pytest.raises(PathError, match="must stay inside"):
        confine(tos_home / ".." / "outside", tos_home, "disk")
    link = tos_home / "escape"
    link.symlink_to(outside)
    with pytest.raises(PathError, match="must stay inside"):
        confine(link, tos_home, "disk")
    with pytest.raises(PathError, match="empty"):
        confine("  ", tos_home, "disk")


def test_home_rejects_filesystem_root(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPLEOS_HOME", "/")
    with pytest.raises(PathError, match="filesystem root"):
        home()
