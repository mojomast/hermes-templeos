"""Hermes plugin entrypoint for TempleOS. Registers the skill and the templeos_* tools."""

from __future__ import annotations

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# Injected via ctx.register_system_prompt_section so the agent can find the
# four templeos_* tools when Hermes Tool Search defers them. Keep this short.
TEMPLEOS_SYSTEM_PROMPT_SECTION = (
    "TempleOS/TinkerOS is driven ONLY with templeos_vm, templeos_screen, "
    "templeos_input, and templeos_files (toolset templeos). Hermes Tool Search "
    "defers plugin tools — if those four are not in your visible tool list, "
    'call tool_search(["templeos"]) or skill_view("templeos:templeos-operator"), '
    "then use them. Never write a VNC client, dial plugin-data sockets, or run "
    "qemu/screendump yourself.\n\n"
    "HolyC one-liner at the T:/Home> prompt: templeos_vm op=status (start if "
    "needed), templeos_screen op=wait_idle then read_text, Esc if AutoComplete "
    "stole focus, templeos_input op=holyc with the source, then wait_idle and "
    "read_text. Report the printed text and the numeric result."
)


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
    if hasattr(ctx, "register_system_prompt_section"):
        # Tool Search defers plugin tools, so the model never sees their
        # descriptions unless we put a short reminder in the system prompt.
        try:
            ctx.register_system_prompt_section(
                "templeos-operator",
                TEMPLEOS_SYSTEM_PROMPT_SECTION,
            )
        except Exception:
            pass

    # Terry companion (tribute): observer hooks drive the pane sprite. No new tools.
    try:
        from templeos.companion import register_hooks as register_companion_hooks

        register_companion_hooks(ctx)
    except Exception:
        pass

    # Pane agent log: wrap handlers even when the dashboard router is not imported.
    try:
        from templeos.api import install_tool_log_hooks

        install_tool_log_hooks()
    except Exception:
        pass
