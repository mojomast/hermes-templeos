"""Hermes plugin entrypoint for TempleOS. Registers the skill and the templeos_* tools."""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def register(ctx) -> None:
    """Register skills/<name>/SKILL.md and the templeos_* tools.

    Keep this fast. Handlers lazy-import nothing heavy at register time; QEMU
    and ISO work happen inside tool calls, not during load.
    """
    skills_dir = Path(__file__).resolve().parent / "skills"
    if skills_dir.is_dir() and hasattr(ctx, "register_skill"):
        for child in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
            skill_md = child / "SKILL.md"
            if skill_md.is_file():
                ctx.register_skill(child.name, skill_md)
    from templeos.tools import register_tools

    register_tools(ctx)
