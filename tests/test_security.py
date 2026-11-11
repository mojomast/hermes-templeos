from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_DIRECT_STORAGE = re.compile(
    r"""localStorage\s*\.\s*(getItem|setItem|removeItem|clear)\s*\(([^)]*)\)"""
)


def _read(*globs: str):
    for pattern in globs:
        for path in ROOT.glob(pattern):
            if path.is_file():
                yield path, path.read_text(errors="replace")


def test_desktop_src_does_not_dial_loopback_or_read_tokens():
    for path, text in _read("desktop/src/**/*.js", "desktop/plugin.js"):
        assert "127.0.0.1" not in text, path
        assert "localhost" not in text, path
        assert "sessionStorage" not in text, path
        assert "document.cookie" not in text, path
        assert "eval(" not in text, path
        assert "new Function" not in text, path
        # Guest screen geometry is the only browser storage the pane may touch.
        if "localStorage" in text:
            assert "templeos.screenSize" in text, path
            for method, arg in _DIRECT_STORAGE.findall(text):
                assert method in {"getItem", "setItem"}, (path, method)
                assert "templeos.screenSize" in arg, (path, arg)


def test_plugin_yaml_declares_no_secrets_and_discloses_qemu():
    text = (ROOT / "plugin.yaml").read_text()
    assert "TEMPLEOS_CHAT_BRIDGE_TOKEN" in text
    assert "requires_env: []" not in text
    assert 'requires_hermes: ">=0.23.0"' in text
    assert "qemu-system-x86_64" in text
    assert "-nic none" in text
    assert "dotenv" not in text


def test_catalog_draft_is_not_a_real_pin():
    draft = (ROOT / "docs" / "catalog" / "templeos.yaml").read_text()
    assert "0000000000000000000000000000000000000000" in draft
    assert "draft" in draft.lower()
    assert 'requires_hermes: ">=0.23.0"' in draft
    assert "spawns qemu-system-x86_64" in draft
    assert "-nic none" in draft
    assert "TEMPLEOS_CHAT_BRIDGE_TOKEN" in draft
    assert "pre_tool_call" in draft
    assert "child hypervisor" in draft
