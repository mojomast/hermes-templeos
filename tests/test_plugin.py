from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

from templeos import PLUGIN_ID, SKILL_ID, __version__
from templeos.tools import TOOL_NAMES, tool_specs
from tests.fakes import FakeCtx

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    spec = importlib.util.spec_from_file_location("templeos_plugin", ROOT / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_manifest_matches_registered_tools_and_skill():
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    ctx = FakeCtx()
    load_plugin().register(ctx)
    assert manifest["name"] == PLUGIN_ID == "templeos"
    assert manifest["version"] == __version__ == "0.2.0"
    assert manifest["requires_hermes"] == ">=0.23.0"
    env = manifest["requires_env"]
    assert [item["name"] if isinstance(item, dict) else item for item in env] == [
        "TEMPLEOS_CHAT_BRIDGE_TOKEN"
    ]
    from templeos.companion import HOOK_NAMES

    assert sorted(manifest["provides_hooks"]) == sorted(HOOK_NAMES)
    assert sorted(ctx.hooks) == sorted(HOOK_NAMES)
    assert sorted(ctx.tools) == sorted(manifest["provides_tools"]) == sorted(TOOL_NAMES)
    assert len(TOOL_NAMES) == 4
    assert "templeos-operator" in ctx.skills
    skill = ctx.skills["templeos-operator"].read_text()
    assert SKILL_ID in skill and skill.startswith("---")
    # Tool Search hides tool schemas; the system prompt section is the visible steer.
    assert "templeos-operator" in ctx.prompt_sections
    section = ctx.prompt_sections["templeos-operator"]["content"]
    assert "tool_search" in section
    assert "VNC" in section
    assert "templeos_input" in section
    assert "op=holyc" in section
    py = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{manifest["version"]}"' in py
    for dep in manifest.get("python_dependencies") or []:
        assert "<" in dep and dep in py


def test_dashboard_manifest_points_at_plugin_api():
    data = json.loads((ROOT / "dashboard" / "manifest.json").read_text())
    assert data["name"] == "templeos"
    assert data["version"] == "0.2.0"
    api = ROOT / "dashboard" / data["api"]
    assert api.is_file()


def test_each_handler_returns_a_json_string():
    for spec in tool_specs():
        raw = spec["handler"]({"op": "not-a-real-op"})
        assert isinstance(raw, str)
        body = json.loads(raw)
        assert body["ok"] is False
        assert body["code"] == "invalid_op"
        assert body["fix"]
