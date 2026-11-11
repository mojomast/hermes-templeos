from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from templeos import diskimage, doctor, flavors
from templeos.envsafe import child_env
from templeos.flavors import get_flavor
from templeos.qemu import find_binary


def test_qemu_version_finds_system_binary(tos_home):
    info = doctor.qemu_version()
    assert info["ok"] is True
    assert info["path"]
    assert Path(info["path"]).name == "qemu-system-x86_64"
    assert info["version"]
    assert "10." in info["version"] or info["version"][0].isdigit()


def test_kvm_usable_requires_open_not_just_exists(tmp_path, monkeypatch):
    missing = tmp_path / "no-kvm"
    assert doctor.kvm_openable(missing) is False
    standin = tmp_path / "fake-kvm"
    standin.write_bytes(b"x")
    standin.chmod(0o600)
    assert doctor.kvm_openable(standin) is True
    # Existence of /dev/kvm is not enough; this box may have the node
    # without grant us access. The public helper must return a bool either way.
    assert isinstance(doctor.kvm_usable(), bool)
    if Path("/dev/kvm").exists() and not doctor.kvm_usable():
        report = doctor.doctor()
        assert report["kvm"]["exists"] is True
        assert report["kvm"]["usable"] is False
        assert "TCG" in report["kvm"]["note"]


def test_doctor_reports_missing_iso_without_fetching(tos_home, monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "download_official", lambda *a, **k: calls.append((a, k)))
    report = doctor.doctor()
    assert calls == []  # default doctor never downloads
    assert report["ok"] is False
    assert report["code"] in {"iso_missing", "iso_hash_mismatch"}
    assert report["iso"]["ok"] is False
    assert report["qemu"]["ok"] is True
    assert report["disk"]["present"] is False
    assert set(report["sockets"]) == {"qmp", "vnc", "com1"}
    assert all(isinstance(v, bool) for v in report["sockets"].values())
    ids = {c["id"] for c in report["checks"]}
    assert {"qemu", "kvm", "iso", "disk"}.issubset(ids)
    assert report["accel_recommended"] in {"tcg", "kvm"}


def test_doctor_reports_disk_image_states_without_fetching(tos_home, monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "download_official", lambda *a, **k: calls.append((a, k)))
    report = doctor.doctor()
    assert calls == []
    assert report["disk_image"]["state"] == "not_downloaded"
    assert report["disk_image"]["url"].startswith("https://github.com/mojomast/temple-of-hermes/releases/download/")
    assert report["disk_image"]["enabled"] is True
    assert any(c["id"] == "disk-image" for c in report["checks"])

    payload = b"tiny-verified-disk"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(diskimage, "DISK_SHA256", digest)
    monkeypatch.setattr(diskimage, "DISK_BYTES", len(payload))
    image = tos_home / diskimage.DISK_FILENAME
    image.write_bytes(payload)
    diskimage.save_config(disk_image="on", disk_image_path=str(image))
    ready = doctor.doctor()
    assert ready["disk_image"]["state"] == "ok"
    assert ready["disk_image"]["verified"] is True
    assert ready["ok"] is True  # Disk boot does not require the live ISO.
    assert calls == []

    bad = tos_home / "bad.qcow2"
    bad.write_bytes(b"wrong")
    diskimage.save_config(disk_image="on", disk_image_path=str(bad))
    report = doctor.doctor()
    assert report["disk_image"]["state"] == "unverified"
    assert report["disk_image"]["verified"] is False


def test_ensure_iso_deletes_hash_mismatch(tos_home, monkeypatch):
    rec = get_flavor("tinkeros")
    dest = tos_home / "isos" / rec["iso_filename"]
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"this is not the official iso")
    result = doctor.ensure_iso("tinkeros", fetch=False)
    assert result["ok"] is False
    assert result["code"] == "iso_hash_mismatch"
    assert not dest.exists()


def test_ensure_iso_accepts_cached_pin(tos_home, monkeypatch):
    rec = get_flavor("tinkeros")
    payload = b"cached-official"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "bytes", len(payload))
    dest = tos_home / "isos" / rec["iso_filename"]
    dest.parent.mkdir(parents=True)
    dest.write_bytes(payload)
    result = doctor.ensure_iso("tinkeros", fetch=False)
    assert result["ok"] is True
    assert result["fetched"] is False
    assert result["sha256"] == digest


def test_ensure_iso_setup_fetches_official_url_only(tos_home, monkeypatch):
    rec = get_flavor("tinkeros")
    payload = b"fetched-official"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "sha256", digest)
    monkeypatch.setitem(flavors.FLAVORS["tinkeros"], "bytes", len(payload))
    seen: dict[str, str] = {}

    def fake_download(url, dest, *, expected_sha256, expected_bytes=None):
        seen["url"] = url
        seen["expected"] = expected_sha256
        Path(dest).write_bytes(payload)
        return Path(dest)

    monkeypatch.setattr(doctor, "download_official", fake_download)
    result = doctor.ensure_iso("tinkeros", fetch=True)
    assert result["ok"] is True and result["fetched"] is True
    assert seen["url"] == rec["url"]
    assert seen["expected"] == digest
    assert (tos_home / "isos" / rec["iso_filename"]).read_bytes() == payload

    report = doctor.doctor(setup=True, flavor="tinkeros")
    # Cached now; setup may call ensure_iso but should still be ok.
    assert report["ok"] is True
    assert report["iso"]["ok"] is True


def test_download_official_rejects_non_public_urls(tmp_path):
    dest = tmp_path / "x.iso"
    with pytest.raises(OSError, match="HTTPS"):
        doctor.download_official("http://example.com/x.iso", dest, expected_sha256="ab")
    with pytest.raises(OSError):
        doctor.download_official("https://127.0.0.1/x.iso", dest, expected_sha256="ab")
    with pytest.raises(OSError):
        doctor.download_official("https://169.254.169.254/x.iso", dest, expected_sha256="ab")
    with pytest.raises(OSError):
        doctor.download_official("file:///etc/passwd", dest, expected_sha256="ab")
    assert not dest.exists()


def test_qemu_version_uses_child_env(monkeypatch, tos_home):
    monkeypatch.setenv("ORBIT_TOKEN", "should-not-leak")
    captured: dict = {}
    real = __import__("subprocess").run

    def wrapped(argv, **kwargs):
        captured["env"] = kwargs.get("env")
        return real(argv, **kwargs)

    monkeypatch.setattr(doctor.subprocess, "run", wrapped)
    info = doctor.qemu_version()
    assert info["ok"] is True
    env = captured["env"]
    assert env is not None
    assert "ORBIT_TOKEN" not in env
    # The allowlist child env is a dict, not os.environ.
    assert env == child_env() or "ORBIT_TOKEN" not in env


def test_unknown_flavor_doctor():
    report = doctor.doctor(flavor="shrine")
    assert report["ok"] is False
    assert report["code"] == "unknown_flavor"


def test_find_binary_consistent_with_doctor():
    path = find_binary()
    info = doctor.qemu_version()
    assert path is not None
    assert str(path) == info["path"]


def test_doctor_setup_fetches_disk_image_when_enabled(tos_home, monkeypatch):
    calls = []
    monkeypatch.setattr(doctor, "ensure_iso", lambda *a, **k: {"ok": False, "state": "missing"}, raising=False)
    monkeypatch.setattr(diskimage, "ensure_image", lambda fetch=True: calls.append(fetch) or {"ok": False})
    try:
        doctor.doctor(setup=True)
    except Exception:
        pass
    assert calls == [True]
    calls.clear()
    diskimage.save_config(disk_image="off")
    try:
        doctor.doctor(setup=True)
    except Exception:
        pass
    assert calls == []
