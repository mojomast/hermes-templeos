"""Tool schemas, JSON envelopes, and handlers.

Every registered handler returns a JSON string envelope
{ok, error, code, fix, ...} — on success, validation failure, and exceptions.
This module is owned by feat/integration; later slices implement the modules
it dispatches to and must not edit this file without coordination.
"""

from __future__ import annotations

import inspect
import json
import re
from typing import Any, Callable

from templeos import PLUGIN_ID
from templeos.arbiter import get_arbiter
from templeos.flavors import FLAVOR_IDS, FlavorError, get_flavor
from templeos.paths import PathError, confine, home

TOOLSET = PLUGIN_ID
TOOL_NAMES = (
    "templeos_vm",
    "templeos_screen",
    "templeos_input",
    "templeos_files",
)

VM_OPS = ("start", "stop", "reset", "snapshot", "restore", "status", "doctor")
SCREEN_OPS = ("look", "read_text", "wait_idle", "hash")
INPUT_OPS = ("type", "keys", "click", "move", "holyc")
FILES_OPS = ("list", "pull", "push")

# Serialized pane/tool JSON budget (base64 + envelope). Matches reviewed Hermes relays.
MAX_ENVELOPE_BYTES = 512 * 1024
HOLYC_MAX_BYTES = 64 * 1024

_UNEXPECTED_KEYWORD = re.compile(
    r"got an unexpected keyword argument '([^']+)'", re.IGNORECASE
)


class Code:
    OK = None
    NOT_IMPLEMENTED = "not_implemented"
    INVALID_OP = "invalid_op"
    INVALID_ARGS = "invalid_args"
    AGENT_PAUSED = "agent_paused"
    PATH_ESCAPE = "path_escape"
    UNKNOWN_FLAVOR = "unknown_flavor"
    VM_NOT_RUNNING = "vm_not_running"
    VM_ALREADY_RUNNING = "vm_already_running"
    QEMU_MISSING = "qemu_missing"
    ISO_MISSING = "iso_missing"
    ISO_HASH_MISMATCH = "iso_hash_mismatch"
    SNAPSHOT_FAILED = "snapshot_failed"
    RESTORE_FAILED = "restore_failed"
    SERIAL_NOT_READY = "serial_not_ready"
    TIMEOUT = "timeout"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    DOCTOR_FAILED = "doctor_failed"
    WATCH_ONLY = "watch_only"


CODE_FIX = {
    Code.NOT_IMPLEMENTED: "This op is contracted; the leased slice will implement it.",
    Code.INVALID_OP: "Use one of the documented ops for this tool.",
    Code.INVALID_ARGS: "Correct the arguments and call the tool again.",
    Code.AGENT_PAUSED: "Wait for the hold-off to end, or ask the user to click Hand back.",
    Code.PATH_ESCAPE: "Choose a path inside the plugin data dir (TEMPLEOS_HOME).",
    Code.UNKNOWN_FLAVOR: "Use flavor tinkeros, templeos, or zealos.",
    Code.VM_NOT_RUNNING: "Call templeos_vm op=start, then retry.",
    Code.VM_ALREADY_RUNNING: "Call templeos_vm op=status, or stop first.",
    Code.QEMU_MISSING: "Install qemu-system-x86_64 (and qemu-img) with your package manager.",
    Code.ISO_MISSING: "Run templeos_vm op=doctor to fetch and pin the official ISO.",
    Code.ISO_HASH_MISMATCH: "Delete the bad ISO and run doctor again so it can re-fetch the pin.",
    Code.SNAPSHOT_FAILED: "Eject non-qcow2 writables and retry snapshot.",
    Code.RESTORE_FAILED: "The plugin must send cont if loadvm left the VM paused, then retry.",
    Code.SERIAL_NOT_READY: "Keep COM1 open and, on TinkerOS, call CommInit then CommInit8n1.",
    Code.TIMEOUT: "Raise the timeout or call wait_idle, then look or read_text again.",
    Code.PAYLOAD_TOO_LARGE: "Use a smaller PNG or crop; the relay budget is 512 KiB JSON.",
    Code.DOCTOR_FAILED: "Read the checks, install QEMU or fix ISO permissions, then retry.",
    Code.WATCH_ONLY: "Switch the pane to Shared or Take control to type.",
}


# --- schemas (keep tight; measured by evals/measure_schemas.py on o200k_base) ---

SCHEMA_VM = {
    "name": "templeos_vm",
    "description": (
        "TempleOS/TinkerOS/ZealOS local QEMU guest lifecycle (start stop reset "
        "snapshot restore status doctor). THE supported boot path — never dial "
        "VNC/QMP sockets yourself. Network always off. snapshot ejects non-qcow2 "
        "writables first; restore issues cont if loadvm left the VM paused. doctor "
        "checks QEMU, ISO pins, and /dev/kvm openability. Sockets are existence "
        "flags only. If deferred behind tool_search, search for templeos vm first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": list(VM_OPS),
                "description": "VM action to perform.",
            },
            "flavor": {
                "type": "string",
                "enum": list(FLAVOR_IDS),
                "description": "Guest OS. Default tinkeros (TinkerOS 5.20-rc10).",
            },
            "name": {
                "type": "string",
                "description": "Snapshot name for snapshot or restore. Default golden.",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
}

SCHEMA_SCREEN = {
    "name": "templeos_screen",
    "description": (
        "TempleOS/TinkerOS guest screen: look (PNG), read_text (serial or 8x8 glyphs), "
        "wait_idle, or hash. Prefer read_text before look. Do NOT write VNC clients or "
        "screendump scripts — those time out; this tool is the supported path. "
        "Full-frame hashes never stabilize (clock/FPS); wait_idle uses a crop. "
        "Default 640x480 PNG. If deferred, tool_search for templeos screen read_text."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": list(SCREEN_OPS),
                "description": "look, read_text, wait_idle, or hash.",
            },
            "timeout_s": {
                "type": "number",
                "description": "Seconds to wait for wait_idle. Default 5.",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
}

SCHEMA_INPUT = {
    "name": "templeos_input",
    "description": (
        "TempleOS/TinkerOS input: type, keys, click, move, or holyc. For a HolyC "
        "one-liner at the T:/Home> prompt, prefer op=holyc with source that prints a "
        "string then an expression (e.g. Hello from Hermes and 6*7). Esc first if "
        "AutoComplete stole focus. click uses VMMouse absolute on TinkerOS. Returns "
        "agent_paused when the user drives or during the ~2s shared hold-off. Never "
        "inject via raw VNC. If deferred, tool_search for templeos holyc input."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": list(INPUT_OPS),
                "description": "type, keys, click, move, or holyc.",
            },
            "text": {
                "type": "string",
                "description": "Characters to type, or HolyC source for op=holyc.",
            },
            "keys": {
                "type": "array",
                "items": {"type": "string"},
                "description": "QEMU qcode names for op=keys (ret, esc, a, shift, ...).",
            },
            "x": {"type": "integer", "description": "Guest X for click or move."},
            "y": {"type": "integer", "description": "Guest Y for click or move."},
            "button": {
                "type": "string",
                "enum": ["left", "right", "middle"],
                "description": "Mouse button for op=click. Default left.",
            },
            "via": {
                "type": "string",
                "enum": ["auto", "vmmouse", "msset", "relative", "serial", "type"],
                "description": "Pointer strategy, or holyc transport. Default auto.",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
}

SCHEMA_FILES = {
    "name": "templeos_files",
    "description": (
        "List, pull, or push files between the host and the guest. Host paths must "
        "stay under the plugin data dir (TEMPLEOS_HOME). Never mount the live RedSea "
        "qcow2 while QEMU has it open."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "op": {
                "type": "string",
                "enum": list(FILES_OPS),
                "description": "list, pull, or push.",
            },
            "path": {
                "type": "string",
                "description": "Guest path to list, pull from, or push to.",
            },
            "src": {
                "type": "string",
                "description": "Confined host path to push.",
            },
            "dest": {
                "type": "string",
                "description": "Confined host path to pull into.",
            },
        },
        "required": ["op"],
        "additionalProperties": False,
    },
}


# --- envelopes ---

def _dump(payload: dict[str, Any]) -> str:
    payload.setdefault("ok", True)
    payload.setdefault("error", None)
    payload.setdefault("code", None)
    payload.setdefault("fix", None)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) > MAX_ENVELOPE_BYTES:
        slim = {
            "ok": False,
            "error": "Tool result exceeded the 512 KiB JSON relay budget.",
            "code": Code.PAYLOAD_TOO_LARGE,
            "fix": CODE_FIX[Code.PAYLOAD_TOO_LARGE],
        }
        return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))
    return text


def ok(**fields: Any) -> str:
    body = {"ok": True, "error": None, "code": None, "fix": None}
    body.update(fields)
    body["ok"] = True
    body["error"] = None
    body["code"] = None
    return _dump(body)


def err(error: str, code: str, fix: str | None = None, **fields: Any) -> str:
    body = {
        "ok": False,
        "error": error,
        "code": code,
        "fix": fix if fix is not None else CODE_FIX.get(code, "See docs/CONTRACTS.md."),
    }
    body.update(fields)
    body["ok"] = False
    return _dump(body)


def not_implemented(unit: str, **fields: Any) -> str:
    return err(
        f"{unit} is contracted but not implemented yet.",
        Code.NOT_IMPLEMENTED,
        **fields,
    )


def _args(params: Any) -> dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, str):
        params = json.loads(params) if params.strip() else {}
    if not isinstance(params, dict):
        raise ValueError("tool arguments must be an object")
    return params


def _require_op(args: dict[str, Any], allowed: tuple[str, ...], tool: str) -> str | tuple[str, str]:
    op = args.get("op")
    if not isinstance(op, str) or not op.strip():
        return err(
            f"{tool} requires op ({', '.join(allowed)}).",
            Code.INVALID_ARGS,
        ), ""
    op = op.strip()
    if op not in allowed:
        return err(
            f"Unknown op {op!r} for {tool}. Use one of: {', '.join(allowed)}.",
            Code.INVALID_OP,
        ), ""
    return op


def _call_impl(fn: Callable[..., Any], *a: Any, **k: Any) -> str:
    try:
        result = fn(*a, **k)
    except NotImplementedError as exc:
        return not_implemented(str(exc) or getattr(fn, "__qualname__", "operation"))
    except PathError as exc:
        return err(str(exc), getattr(exc, "code", Code.PATH_ESCAPE))
    except FlavorError as exc:
        return err(str(exc), getattr(exc, "code", Code.UNKNOWN_FLAVOR))
    except ValueError as exc:
        return err(str(exc), Code.INVALID_ARGS)
    except Exception as exc:
        envelope = getattr(exc, "envelope", None)
        if isinstance(envelope, dict) and envelope.get("code"):
            return err(
                str(envelope.get("error") or exc),
                str(envelope.get("code") or "internal_error"),
                envelope.get("fix"),
                **{k: v for k, v in envelope.items() if k not in {"ok", "error", "code", "fix"}},
            )
        return err(
            "Internal error while running the tool.",
            "internal_error",
            "Retry once; if it persists, check doctor and the plugin log.",
            # Never include traceback in the tool result (may leak paths/env).
        )
    if isinstance(result, str):
        try:
            json.loads(result)
        except ValueError:
            return err("Implementation returned a non-JSON string.", "internal_error")
        return result
    if not isinstance(result, dict):
        return err("Implementation returned a non-object result.", "internal_error")
    if result.get("ok") is False:
        return err(
            str(result.get("error") or "The operation failed."),
            str(result.get("code") or "internal_error"),
            result.get("fix"),
            **{k: v for k, v in result.items() if k not in {"ok", "error", "code", "fix"}},
        )
    return ok(**{k: v for k, v in result.items() if k not in {"ok", "error", "code", "fix"}})


# --- handlers ---

def handle_vm(params: Any) -> str:
    try:
        args = _args(params)
    except (ValueError, json.JSONDecodeError) as exc:
        return err(str(exc), Code.INVALID_ARGS)
    got = _require_op(args, VM_OPS, "templeos_vm")
    if not isinstance(got, str):
        return got[0]
    op = got
    flavor = args.get("flavor") or "tinkeros"
    try:
        get_flavor(flavor)
    except FlavorError as exc:
        return err(str(exc), exc.code)
    name = args.get("name") or "golden"
    if not isinstance(name, str) or not name.strip() or "/" in name or "\\" in name or ".." in name:
        return err("name must be a simple snapshot id (default golden).", Code.INVALID_ARGS)

    if op == "start":
        from templeos.vm import start as impl
        return _call_impl(impl, flavor=flavor, snapshot=name)
    if op == "stop":
        from templeos.vm import stop as impl
        return _call_impl(impl)
    if op == "reset":
        from templeos.vm import reset as impl
        return _call_impl(impl)
    if op == "snapshot":
        from templeos.vm import snapshot as impl
        return _call_impl(impl, name)
    if op == "restore":
        from templeos.vm import restore as impl
        return _call_impl(impl, name)
    if op == "status":
        from templeos.vm import status as impl
        return _call_impl(impl)
    if op == "doctor":
        from templeos.doctor import doctor as impl
        return _call_impl(impl)
    return err(f"Unknown op {op!r}.", Code.INVALID_OP)


def handle_screen(params: Any) -> str:
    try:
        args = _args(params)
    except (ValueError, json.JSONDecodeError) as exc:
        return err(str(exc), Code.INVALID_ARGS)
    got = _require_op(args, SCREEN_OPS, "templeos_screen")
    if not isinstance(got, str):
        return got[0]
    op = got
    timeout_s = args.get("timeout_s", 5)
    if op == "wait_idle":
        try:
            timeout_s = float(timeout_s)
        except (TypeError, ValueError):
            return err("timeout_s must be a number.", Code.INVALID_ARGS)
        if timeout_s < 0 or timeout_s > 120:
            return err("timeout_s must be between 0 and 120.", Code.INVALID_ARGS)
        from templeos.screen import wait_idle as impl
        return _call_impl(impl, timeout_s=timeout_s)
    if op == "look":
        from templeos.screen import look as impl
        return _call_impl(impl)
    if op == "read_text":
        from templeos.screen import read_text as impl
        return _call_impl(impl)
    if op == "hash":
        from templeos.screen import frame_hash as impl
        return _call_impl(impl)
    return err(f"Unknown op {op!r}.", Code.INVALID_OP)


def handle_input(params: Any) -> str:
    try:
        args = _args(params)
    except (ValueError, json.JSONDecodeError) as exc:
        return err(str(exc), Code.INVALID_ARGS)
    got = _require_op(args, INPUT_OPS, "templeos_input")
    if not isinstance(got, str):
        return got[0]
    op = got
    arbiter = get_arbiter()
    with arbiter.queue():
        allowed, paused = arbiter.agent_may_input()
        if not allowed and paused is not None:
            return _dump(paused)
        if op == "type":
            text = args.get("text")
            if not isinstance(text, str) or text == "":
                return err("op=type requires text.", Code.INVALID_ARGS)
            from templeos.input import type_text as impl
            return _call_impl(impl, text)
        if op == "keys":
            keys = args.get("keys")
            if not isinstance(keys, list) or not keys or not all(isinstance(k, str) and k for k in keys):
                return err("op=keys requires a non-empty keys array of qcode names.", Code.INVALID_ARGS)
            from templeos.input import send_keys as impl
            return _call_impl(impl, keys)
        if op in ("click", "move"):
            if not isinstance(args.get("x"), int) or not isinstance(args.get("y"), int):
                return err(f"op={op} requires integer x and y.", Code.INVALID_ARGS)
            via = args.get("via") or "auto"
            if op == "click":
                button = args.get("button") or "left"
                if button not in ("left", "right", "middle"):
                    return err("button must be left, right, or middle.", Code.INVALID_ARGS)
                from templeos.input import click as impl
                return _call_impl(impl, args["x"], args["y"], button=button, via=via)
            from templeos.input import move as impl
            return _call_impl(impl, args["x"], args["y"], via=via)
        if op == "holyc":
            text = args.get("text")
            if not isinstance(text, str) or text == "":
                return err("op=holyc requires text (HolyC source).", Code.INVALID_ARGS)
            if len(text.encode("utf-8")) > HOLYC_MAX_BYTES:
                return err(
                    f"HolyC source exceeds {HOLYC_MAX_BYTES} bytes.",
                    Code.INVALID_ARGS,
                    "Shorten the source and send it in smaller chunks.",
                )
            via = args.get("via") or "auto"
            from templeos.input import holyc as impl
            return _call_impl(impl, text, via=via)
    return err(f"Unknown op {op!r}.", Code.INVALID_OP)


def handle_files(params: Any) -> str:
    try:
        args = _args(params)
    except (ValueError, json.JSONDecodeError) as exc:
        return err(str(exc), Code.INVALID_ARGS)
    got = _require_op(args, FILES_OPS, "templeos_files")
    if not isinstance(got, str):
        return got[0]
    op = got
    try:
        root = home()
    except PathError as exc:
        return err(str(exc), exc.code)
    if op == "list":
        path = args.get("path") or "T:/"
        if not isinstance(path, str) or not path.strip():
            return err("op=list requires a guest path (default T:/).", Code.INVALID_ARGS)
        from templeos.files import list_guest as impl
        return _call_impl(impl, path)
    if op == "pull":
        guest = args.get("path")
        dest = args.get("dest")
        if not isinstance(guest, str) or not guest.strip():
            return err("op=pull requires a guest path.", Code.INVALID_ARGS)
        if not isinstance(dest, str) or not dest.strip():
            return err("op=pull requires dest (a host path under the plugin data dir).", Code.INVALID_ARGS)
        try:
            dest_p = confine(dest, root, "dest")
        except PathError as exc:
            return err(str(exc), exc.code)
        from templeos.files import pull as impl
        return _call_impl(impl, guest, dest_p)
    if op == "push":
        guest = args.get("path")
        src = args.get("src")
        if not isinstance(guest, str) or not guest.strip():
            return err("op=push requires a guest path.", Code.INVALID_ARGS)
        if not isinstance(src, str) or not src.strip():
            return err("op=push requires src (a host path under the plugin data dir).", Code.INVALID_ARGS)
        try:
            src_p = confine(src, root, "src")
        except PathError as exc:
            return err(str(exc), exc.code)
        from templeos.files import push as impl
        return _call_impl(impl, src_p, guest)
    return err(f"Unknown op {op!r}.", Code.INVALID_OP)


HANDLERS = {
    "templeos_vm": handle_vm,
    "templeos_screen": handle_screen,
    "templeos_input": handle_input,
    "templeos_files": handle_files,
}

SCHEMAS = {
    "templeos_vm": SCHEMA_VM,
    "templeos_screen": SCHEMA_SCREEN,
    "templeos_input": SCHEMA_INPUT,
    "templeos_files": SCHEMA_FILES,
}


def tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "schema": SCHEMAS[name],
            "handler": HANDLERS[name],
            "description": SCHEMAS[name]["description"],
        }
        for name in TOOL_NAMES
    ]


def _signature_parameters(register: Callable) -> dict[str, inspect.Parameter]:
    try:
        return dict(inspect.signature(register).parameters)
    except (TypeError, ValueError):
        return {}


def _accepts(register: Callable, key: str, parameters: dict[str, inspect.Parameter]) -> bool:
    if not parameters:
        return True
    if key in parameters:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in parameters.values())


def _call_register_tool(register: Callable, **kwargs: Any) -> None:
    """Keyword-only register; drop output_schema on Hermes 0.21.7 rather than aborting."""
    parameters = _signature_parameters(register)
    dropped = {key for key in kwargs if not _accepts(register, key, parameters)}
    last_error: TypeError | None = None
    for _ in range(1 + len(kwargs)):
        payload = {k: v for k, v in kwargs.items() if k not in dropped}
        try:
            register(**payload)
            return
        except TypeError as exc:
            last_error = exc
            match = _UNEXPECTED_KEYWORD.search(str(exc))
            if match is None:
                raise
            name = match.group(1)
            if name not in kwargs or name in dropped:
                raise
            dropped.add(name)
    if last_error is not None:
        raise last_error


def register_tools(ctx) -> None:
    """Register the four tools. Names must match plugin.yaml provides_tools."""
    try:
        from templeos.api import install_tool_log_hooks

        install_tool_log_hooks()
    except Exception:
        pass
    register = ctx.register_tool
    for spec in tool_specs():
        handler = HANDLERS.get(spec["name"], spec["handler"])
        _call_register_tool(
            register,
            name=spec["name"],
            toolset=TOOLSET,
            schema=spec["schema"],
            handler=handler,
            description=spec["description"],
        )
