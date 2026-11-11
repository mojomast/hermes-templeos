"""TempleOS Hermes plugin package."""

from __future__ import annotations

from typing import Any

__version__ = "0.2.0"
PLUGIN_ID = "templeos"
SKILL_ID = "templeos:templeos-operator"
DISPLAY_NAME = "TempleOS"


def register_nudge_hooks(ctx: Any) -> list[str]:
    """Register the pending-only pre_llm_call nudge, if hooks are supported."""
    try:
        from templeos.nudge import register_hooks
    except Exception:
        return []
    try:
        return register_hooks(ctx)
    except Exception:
        return []
