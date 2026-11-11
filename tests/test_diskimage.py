from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from templeos import diskimage
from templeos.paths import disks_dir


def _pin(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(diskimage, "DISK_SHA256", digest)
    monkeypatch.setattr(diskimage, "DISK_BYTES", len(payload))
    return digest


def _image(tmp_path: Path, payload: bytes = b"pinned-disk-image") -> Path:
    path = tmp_path / diskimage.DISK_FILENAME
    path.write_bytes(payload)
    return path


def test_pinned_record_points_at_official_release_asset():
    rec = diskimage.record()
    assert rec["id"] == "templeoh-disk"
    assert rec["flavor"] == "templeoh"
    assert rec["filename"] == "TempleOfHermes-0.1.3-disk.qcow2"
    assert rec["sha256"] == "d81a3c189093bd0edddad50b7a55d6582d0490204d63720e14fc5fb9d901f1aa"
    assert rec["size"] == 11_107_840
    assert rec["url"] == (
        "https://github.com/mojomast/temple-of-hermes/releases/download/"
        "v0.1.3/TempleOfHermes-0.1.3-disk.qcow2"
    )
    assert diskimage.FUTURE_DISK_IMAGE_URL == diskimage.DISK_IMAGE_URL


def test_verify_accepts_pinned_size_and_sha(tmp_path, monkeypatch):
    payload = b"verified-disk"
    digest = _pin(monkeypatch, payload)
    image = _image(tmp_path, payload)
    info = diskimage.verify(image)
    assert info["ok"] is True
    assert info["state"] == "ok"
    assert info["sha256"] == digest
    assert info["bytes"] == len(payload)
    assert info["path"] == str(image)


def test_verify_refuses_size_and_hash_mismatch(tmp_path, monkeypatch):
    payload = b"expected-disk"
    _pin(monkeypatch, payload)
    short = tmp_path / "short.qcow2"
    short.write_bytes(b"x")
    size = diskimage.verify(short)
    assert size["ok"] is False
    assert size["state"] == "unverified"
    assert size["code"] == "disk_image_size_mismatch"

    wrong = tmp_path / "wrong.qcow2"
    wrong.write_bytes(b"tampered-disk")
    bad = diskimage.verify(wrong)
    assert bad["ok"] is False
    assert bad["state"] == "unverified"
    assert bad["code"] == "disk_image_hash_mismatch"


def test_missing_image_is_structured_not_a_crash(tmp_path, monkeypatch):
    _pin(monkeypatch, b"payload")
    info = diskimage.verify(tmp_path / "absent.qcow2")
    assert info["ok"] is False
    assert info["state"] == "missing"
    assert info["code"] == "disk_image_missing"
    assert info["path_set"] is True


def test_default_on_and_not_downloaded_until_fetch(tos_home):
    info = diskimage.status()
    assert info["enabled"] is True
    assert info["state"] == "not_downloaded"
    assert info["verified"] is False
    assert info["url"] == diskimage.DISK_IMAGE_URL
    assert "next start" in info["text"].lower()


def test_unpublished_status_when_url_cleared(tos_home, monkeypatch):
    monkeypatch.setattr(diskimage, "DISK_IMAGE_URL", None)
    info = diskimage.status()
    assert info["state"] == "unpublished"
    assert info["url"] is None


def test_ensure_image_downloads_and_verifies_into_cache(tos_home, monkeypatch):
    payload = b"downloaded-pinned-disk"
    _pin(monkeypatch, payload)
    seen = []

    def fake_download(url, dest):
        seen.append(url)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(payload)
        return Path(dest)

    monkeypatch.setattr(diskimage, "download_image", fake_download)
    info = diskimage.ensure_image(fetch=True)
    assert info["ok"] is True and info["state"] == "ok"
    assert seen == [diskimage.DISK_IMAGE_URL]
    assert Path(info["path"]) == diskimage.cached_path()
    # Cached and verified: no second download.
    assert diskimage.ensure_image(fetch=True)["ok"] is True
    assert len(seen) == 1


def test_corrupt_cache_is_redownloaded(tos_home, monkeypatch):
    payload = b"good-disk"
    _pin(monkeypatch, payload)
    cache = diskimage.cached_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"bad-disk!")

    def fake_download(url, dest):
        Path(dest).write_bytes(payload)
        return Path(dest)

    monkeypatch.setattr(diskimage, "download_image", fake_download)
    assert diskimage.verify()["state"] == "unverified"
    assert diskimage.ensure_image(fetch=True)["ok"] is True


def test_download_failure_is_a_status_not_an_error(tos_home):
    info = diskimage.ensure_image(fetch=True)
    assert info["ok"] is False
    assert info["state"] == "download_failed"
    assert info["code"] == "disk_image_download_failed"
    assert not diskimage.cached_path().exists()


def test_config_persists_toggle_and_path(tos_home):
    saved = diskimage.save_config(disk_image="on", disk_image_path="/tmp/example.qcow2")
    assert saved["disk_image"] == "on"
    assert saved["disk_image_path"] == "/tmp/example.qcow2"
    data = json.loads((tos_home / "settings.json").read_text())
    assert data["disk_image"] == "on"
    assert data["disk_image_path"] == "/tmp/example.qcow2"
    assert diskimage.enabled() is True
    off = diskimage.save_config(disk_image=False)
    assert off["disk_image"] == "off"
    with pytest.raises(ValueError):
        diskimage.save_config(disk_image="maybe")


def test_env_path_overrides_config(tos_home, monkeypatch):
    diskimage.save_config(disk_image="on", disk_image_path="/tmp/config.qcow2")
    monkeypatch.setenv("TEMPLEOS_DISK_IMAGE", "/tmp/env.qcow2")
    cfg = diskimage.load_config()
    assert cfg["effective_path"] == "/tmp/env.qcow2"
    assert cfg["path_source"] == "env"


def test_overlay_creation_command_uses_backing_file(tos_home, tmp_path, monkeypatch):
    base = _image(tmp_path)
    overlay = disks_dir() / "templeoh-disk-overlay.qcow2"
    seen: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["env"] = kwargs.get("env")
        Path(argv[-1]).write_bytes(b"qcow2")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(diskimage, "run_command", fake_run)
    made = diskimage.ensure_overlay(base, overlay)
    assert made == overlay
    assert made.is_file()
    argv = seen["argv"]
    assert Path(argv[0]).name == "qemu-img"
    assert argv[1:] == [
        "create",
        "-f",
        "qcow2",
        "-b",
        str(base),
        "-F",
        "qcow2",
        str(overlay),
    ]
    assert seen["env"] is not None
    # Reuse is quiet and never rewrites an existing overlay.
    seen.clear()
    assert diskimage.ensure_overlay(base, overlay) == overlay
    assert seen == {}


def test_overlay_failure_removes_partial(tmp_path, monkeypatch):
    base = _image(tmp_path)
    overlay = tmp_path / "overlay.qcow2"

    def fake_run(argv, **kwargs):
        Path(argv[-1]).write_bytes(b"partial")
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"backing file missing")

    monkeypatch.setattr(diskimage, "run_command", fake_run)
    with pytest.raises(RuntimeError, match="backing file missing"):
        diskimage.ensure_overlay(base, overlay, replace=True)
    assert not overlay.exists()


def test_boot_plan_falls_back_when_off_or_download_fails(tos_home, monkeypatch):
    diskimage.save_config(disk_image="off")
    off = diskimage.boot_plan("templeoh")
    assert off["mode"] == "iso"
    assert off["reason"] == "option_off"

    diskimage.save_config(disk_image="on")
    failed = diskimage.boot_plan("templeoh")
    assert failed["mode"] == "iso"
    assert failed["fallback"] is True
    assert failed["reason"] == "download_failed"

    other = diskimage.boot_plan("tinkeros")
    assert other["mode"] == "iso"
    assert other["reason"] == "flavor_not_templeoh"


def test_boot_plan_downloads_then_selects_overlay(tos_home, monkeypatch):
    payload = b"fetched-at-boot"
    _pin(monkeypatch, payload)

    def fake_download(url, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(payload)
        return Path(dest)

    monkeypatch.setattr(diskimage, "download_image", fake_download)
    plan = diskimage.boot_plan("templeoh")
    assert plan["mode"] == "disk"
    assert plan["base"] == diskimage.cached_path()


def test_boot_plan_selects_overlay_when_verified(tos_home, tmp_path, monkeypatch):
    payload = b"bootable-pinned-disk"
    _pin(monkeypatch, payload)
    image = _image(tmp_path, payload)
    diskimage.save_config(disk_image="on", disk_image_path=str(image))
    plan = diskimage.boot_plan("templeoh")
    assert plan["mode"] == "disk"
    assert plan["base"] == image
    assert plan["overlay"] == disks_dir() / "templeoh-disk-overlay.qcow2"
    assert plan["status"]["state"] == "ok"
