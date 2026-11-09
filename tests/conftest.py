"""Shared fixtures: isolated TEMPLEOS_HOME and a fresh arbiter."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tos_home(tmp_path, monkeypatch):
    home = tmp_path / "tos-home"
    home.mkdir()
    monkeypatch.setenv("TEMPLEOS_HOME", str(home))
    from templeos.arbiter import reset_arbiter

    reset_arbiter()
    return home
