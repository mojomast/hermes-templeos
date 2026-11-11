"""Unit test for the temple-session token-budget eval.

The eval is host-side only: no QEMU, no network, no live BBS.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL_PATH = ROOT / "evals" / "temple_session_budget.py"


@pytest.fixture(scope="module")
def budget():
    pytest.importorskip("tiktoken")
    spec = importlib.util.spec_from_file_location("temple_session_budget", EVAL_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_session_payload_under_documented_budget(budget):
    counts = budget.measure()
    assert set(counts) == {"skill", "session_start", "digest", "journal", "total"}
    for name in ("skill", "session_start", "digest", "journal"):
        assert counts[name] > 0, f"{name} fixture measured zero tokens"
    assert counts["total"] == sum(
        counts[name] for name in ("skill", "session_start", "digest", "journal")
    )
    assert budget.violations(counts) == []


def test_over_budget_is_rejected(budget):
    counts = budget.measure()
    assert budget.violations(counts, caps={"skill": 0}, total_cap=10**9)
    assert budget.violations(counts, caps={}, total_cap=1)


def test_eval_script_exits_zero(budget):
    pytest.importorskip("tiktoken")
    proc = subprocess.run(
        [sys.executable, str(EVAL_PATH)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "total" in proc.stdout
