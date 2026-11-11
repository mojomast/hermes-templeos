from __future__ import annotations

import json
from pathlib import Path

from templeos.tools import FILES_OPS, INPUT_OPS, SCREEN_OPS, TOOL_NAMES, VM_OPS, HANDLERS, tool_specs

ROOT = Path(__file__).resolve().parents[1]


def test_every_documented_op_returns_a_json_envelope(tos_home):
    samples = {
        "templeos_vm": [{"op": op} for op in VM_OPS],
        "templeos_screen": [{"op": op} for op in SCREEN_OPS],
        "templeos_input": [
            {"op": "type", "text": "Hi"},
            {"op": "keys", "keys": ["ret"]},
            {"op": "click", "x": 10, "y": 20},
            {"op": "move", "x": 10, "y": 20},
            {"op": "holyc", "text": "Dir;"},
        ],
        "templeos_files": [
            {"op": "list", "path": "T:/"},
            {"op": "pull", "path": "T:/Home/X.HC", "dest": str(tos_home / "X.HC")},
            {"op": "push", "path": "T:/Home/X.HC", "src": str(tos_home / "X.HC")},
        ],
    }
    (tos_home / "X.HC").write_text("// hi\n")
    seen = {name: set() for name in TOOL_NAMES}
    for spec in tool_specs():
        for args in samples[spec["name"]]:
            raw = spec["handler"](args)
            assert isinstance(raw, str), spec["name"]
            body = json.loads(raw)
            assert set(body) >= {"ok", "error", "code", "fix"}
            assert body["ok"] in (True, False)
            if body["ok"] is False:
                assert body["code"]
                assert body["fix"]
            else:
                assert body["code"] is None
                assert body["error"] is None
            seen[spec["name"]].add(args["op"])
    assert seen["templeos_vm"] == set(VM_OPS)
    assert seen["templeos_screen"] == set(SCREEN_OPS)
    assert seen["templeos_input"] == set(INPUT_OPS)
    assert seen["templeos_files"] == set(FILES_OPS)


def test_leases_table_names_all_slices():
    text = (ROOT / "docs" / "CONTRACTS.md").read_text()
    assert "feat/vm" in text
    assert "feat/screen-input" in text
    assert "feat/pane" in text
    assert "feat/files-docs" in text
    assert "feat/integration" in text
    assert "templeos/tools.py" in text
    assert "tests/fakes.py" in text
    for name in HANDLERS:
        assert name in text


def test_schema_budget_under_2000_o200k():
    import sys
    sys.path.insert(0, str(ROOT))
    from evals.measure_schemas import schema_tokens
    n = schema_tokens()
    assert n < 2000, f"schema tokens {n} exceed the ~2000 o200k budget"
    assert n > 200, f"schema tokens {n} look too small; schemas may have failed to load"
