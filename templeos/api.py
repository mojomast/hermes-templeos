"""Backend routes for the Desktop pane.

Mounted at /api/plugins/templeos/ (see dashboard/plugin_api.py). The pane
calls these only through ctx.rest. This process is the only one that opens
QEMU unix sockets. Never print tokens; there is no sidecar token for the
iframe to read.

Slice C (feat/pane) owns this module: status, start/stop/reset, snapshots,
cheap frame polling (sha256 / ETag, 512 KiB cap), user input (arbiter
hold-off), control mode, doctor setup, and the agent activity log.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable

from templeos import PLUGIN_ID, __version__
from templeos.arbiter import get_arbiter
from templeos.flavors import DEFAULT, FLAVOR_IDS, FlavorError, get_flavor
from templeos.tools import CODE_FIX, Code, err

try:
    from fastapi import APIRouter, Request
except ImportError:  # pragma: no cover - fastapi is optional outside Hermes
    APIRouter = None
    Request = None

# Whole serialized JSON (base64 + envelope) must stay under this budget.
MAX_FRAME_JSON_BYTES = 512 * 1024
LOG_MAX = 40
AGENT_BUSY_S = 1.5
GOLDEN = "golden"
SOFT_FRAME_CODES = {
    Code.NOT_IMPLEMENTED,
    Code.VM_NOT_RUNNING,
}

ROUTE_HEALTH = "/health"
ROUTE_STATUS = "/status"
ROUTE_FRAME = "/frame"
ROUTE_INPUT = "/input"
ROUTE_CONTROL = "/control"
ROUTE_VM = "/vm"
ROUTE_SNAPSHOTS = "/snapshots"
ROUTE_LOG = "/log"
ROUTE_SETUP = "/setup"
ROUTE_DOCTOR = "/doctor"

_LOG_LOCK = threading.Lock()
_LOG: deque[dict[str, Any]] = deque(maxlen=LOG_MAX)
_LOG_SEQ = 0

_HOOKS_INSTALLED = False


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def reset_activity_log() -> None:
    """Clear the in-process activity log (tests)."""
    global _LOG_SEQ
    with _LOG_LOCK:
        _LOG.clear()
        _LOG_SEQ = 0


def note_agent_action(
    tool: str,
    op: str = "",
    *,
    ok: bool = True,
    code: str | None = None,
    summary: str | None = None,
    source: str = "agent",
) -> dict[str, Any]:
    """Append one tool/pane action to the activity log. Safe to call from tools.py."""
    global _LOG_SEQ
    clock = time.time()
    event = {
        "id": 0,
        "ts": clock,
        "at": _utc_iso(clock),
        "source": source if source in ("agent", "user") else "agent",
        "tool": str(tool or ""),
        "op": str(op or ""),
        "ok": bool(ok),
        "code": code,
        "summary": summary or " ".join(part for part in (tool, op) if part).strip() or str(tool or "action"),
    }
    with _LOG_LOCK:
        _LOG_SEQ += 1
        event["id"] = _LOG_SEQ
        _LOG.append(event)
        return dict(event)


def activity_events(*, limit: int | None = None, now: float | None = None) -> list[dict[str, Any]]:
    cap = LOG_MAX if limit is None else max(0, int(limit))
    with _LOG_LOCK:
        rows = list(_LOG)[-cap:]
    return rows


def agent_is_busy(*, now: float | None = None) -> bool:
    clock = time.time() if now is None else now
    with _LOG_LOCK:
        events = list(_LOG)
    for event in reversed(events):
        if event.get("source") != "agent":
            continue
        return (clock - float(event.get("ts") or 0)) < AGENT_BUSY_S
    return False


def _wrap_tool_handler(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    def wrapped(params: Any = None, *args: Any, **kwargs: Any) -> Any:
        raw = fn(params, *args, **kwargs)
        try:
            args_obj = params if isinstance(params, dict) else {}
            body = json.loads(raw) if isinstance(raw, str) else {}
            if not isinstance(body, dict):
                body = {}
            note_agent_action(
                tool=name,
                op=str(args_obj.get("op") or ""),
                ok=bool(body.get("ok")),
                code=body.get("code"),
            )
        except Exception:
            pass
        return raw

    wrapped.__wrapped__ = fn  # type: ignore[attr-defined]
    wrapped.__name__ = getattr(fn, "__name__", name)
    wrapped.__doc__ = getattr(fn, "__doc__", None)
    return wrapped


def install_tool_log_hooks() -> bool:
    """Wrap templeos.tools.HANDLERS so agent tool calls appear in GET /log.

    tools.py is integration-owned, so this is a runtime hook rather than an
    edit of that file. Idempotent.
    """
    global _HOOKS_INSTALLED
    if _HOOKS_INSTALLED:
        return False
    from templeos import tools

    if getattr(tools, "_templeos_pane_log_hooks", False):
        _HOOKS_INSTALLED = True
        return False
    for name, fn in list(tools.HANDLERS.items()):
        if getattr(fn, "__wrapped__", None) is not None and getattr(fn, "__name__", "") != name:
            continue
        tools.HANDLERS[name] = _wrap_tool_handler(name, fn)
    tools._templeos_pane_log_hooks = True  # type: ignore[attr-defined]
    _HOOKS_INSTALLED = True
    return True


def _json_ok(**fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"ok": True, "error": None, "code": None, "fix": None}
    body.update(fields)
    body["ok"] = True
    body["error"] = None
    body["code"] = None
    body["fix"] = None
    return body


def _json_err(message: str, code: str, fix: str | None = None, **fields: Any) -> dict[str, Any]:
    return json.loads(err(message, code, fix, **fields))


def _from_impl(fn: Callable[..., Any], *args: Any, unit: str = "operation", **kwargs: Any) -> dict[str, Any]:
    try:
        result = fn(*args, **kwargs)
    except NotImplementedError as exc:
        return _json_err(
            str(exc) or f"{unit} is contracted but not implemented yet.",
            Code.NOT_IMPLEMENTED,
        )
    except FlavorError as exc:
        return _json_err(str(exc), getattr(exc, "code", Code.UNKNOWN_FLAVOR))
    except ValueError as exc:
        return _json_err(str(exc), Code.INVALID_ARGS)
    except Exception:
        return _json_err(
            f"{unit} failed.",
            Code.DOCTOR_FAILED,
            CODE_FIX[Code.DOCTOR_FAILED],
        )
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except ValueError:
            return _json_err("Implementation returned a non-JSON string.", "internal_error")
    if not isinstance(result, dict):
        return _json_err("Implementation returned a non-object result.", "internal_error")
    if result.get("ok") is False:
        body = dict(result)
        body["ok"] = False
        body.setdefault("error", f"{unit} failed.")
        body.setdefault("code", "internal_error")
        body.setdefault("fix", CODE_FIX.get(body.get("code") or "", "See docs/CONTRACTS.md."))
        return body
    body = _json_ok()
    body.update({k: v for k, v in result.items() if k not in {"ok", "error", "code", "fix"}})
    return body


def _snapshot_name(raw: Any, *, default: str = GOLDEN) -> tuple[str | None, dict[str, Any] | None]:
    if raw is None or raw == "":
        name = default
    elif not isinstance(raw, str):
        return None, _json_err("name must be a simple snapshot id (default golden).", Code.INVALID_ARGS)
    else:
        name = raw.strip() or default
    if not name or "/" in name or "\\" in name or ".." in name:
        return None, _json_err("name must be a simple snapshot id (default golden).", Code.INVALID_ARGS)
    return name, None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _flavor_or_err(raw: Any) -> tuple[str | None, dict[str, Any] | None]:
    try:
        rec = get_flavor(raw)
    except FlavorError as exc:
        return None, _json_err(str(exc), getattr(exc, "code", Code.UNKNOWN_FLAVOR))
    return str(rec["id"]), None


def _check_flag(checks: Any, *names: str) -> Any:
    if not isinstance(checks, dict):
        return None
    for name in names:
        if name in checks:
            return checks[name]
    return None


def _flag_missing(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, str) and value.lower() in {"missing", "false", "no", "absent", "error"}:
        return True
    if isinstance(value, dict) and value.get("ok") is False:
        return True
    return False


def _setup_needed(checks: Any, doctor: dict[str, Any] | None, code: str | None) -> bool:
    if code in {Code.QEMU_MISSING, Code.ISO_MISSING, Code.ISO_HASH_MISMATCH, Code.DOCTOR_FAILED}:
        return True
    if doctor is not None and doctor.get("ok") is False:
        return True
    qemu = _check_flag(checks, "qemu", "qemu_present", "qemu-system-x86_64")
    iso = _check_flag(checks, "iso", "iso_present", "iso_ok")
    return _flag_missing(qemu) or _flag_missing(iso)


def _empty_sockets() -> dict[str, bool]:
    return {"qmp": False, "vnc": False, "com1": False}


def _sanitize_sockets(raw: Any) -> dict[str, bool]:
    base = _empty_sockets()
    if not isinstance(raw, dict):
        return base
    for key in base:
        value = raw.get(key)
        # Existence flags only; never pass through paths or tokens.
        base[key] = True if value is True else False
    return base


def _apply_flavor_dims(body: dict[str, Any], flavor: str) -> None:
    try:
        rec = get_flavor(flavor)
    except FlavorError:
        rec = get_flavor(DEFAULT)
    body["flavor"] = rec["id"]
    body["flavor_name"] = rec["name"]
    body["width"] = int(rec["width"])
    body["height"] = int(rec["height"])


def health_payload() -> dict[str, Any]:
    snap = get_arbiter().snapshot()
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "plugin": PLUGIN_ID,
        "version": __version__,
        "mode": snap["mode"],
        "agent_paused": snap["agent_paused"],
        "agent_busy": agent_is_busy(),
        "hold_off_s": snap["hold_off_s"],
        "user_may_input": snap["user_may_input"],
    }


def _doctor_report() -> dict[str, Any]:
    from templeos import doctor

    return _from_impl(doctor.doctor, unit="doctor")


def status_payload() -> dict[str, Any]:
    """Arbiter + doctor readiness + VM status when Slice A is present."""
    snap = get_arbiter().snapshot()
    body: dict[str, Any] = {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "plugin": PLUGIN_ID,
        "version": __version__,
        "running": False,
        "flavor": DEFAULT,
        "flavor_name": get_flavor(DEFAULT)["name"],
        "accel": None,
        "snapshot": None,
        "snapshots": [GOLDEN],
        "kvm": False,
        "sockets": _empty_sockets(),
        "ready": False,
        "setup_needed": False,
        "checks": {},
        "vm_implemented": False,
        "width": 640,
        "height": 480,
        "agent_busy": agent_is_busy(),
        **snap,
    }
    _apply_flavor_dims(body, body["flavor"])

    doctor_body: dict[str, Any] | None = None
    try:
        from templeos import doctor as doctor_mod

        doctor_body = _from_impl(doctor_mod.doctor, unit="doctor")
        if doctor_body.get("code") != Code.NOT_IMPLEMENTED:
            checks = doctor_body.get("checks") if isinstance(doctor_body.get("checks"), dict) else {}
            body["checks"] = checks
            if "kvm" in doctor_body:
                body["kvm"] = bool(doctor_body.get("kvm"))
            elif "kvm" in checks:
                body["kvm"] = bool(checks.get("kvm")) and not _flag_missing(checks.get("kvm"))
            if doctor_body.get("ok") is False:
                body["setup_needed"] = True
                if doctor_body.get("code"):
                    body["code"] = doctor_body.get("code")
                    body["error"] = doctor_body.get("error")
                    body["fix"] = doctor_body.get("fix")
                    # Status itself still answers; the pane uses setup_needed / code.
                    body["ok"] = True
            else:
                body["ready"] = True
        else:
            body["checks"] = {"qemu": "unknown", "iso": "unknown", "kvm": "unknown"}
            body["setup_needed"] = True
    except Exception:
        body["checks"] = {"qemu": "unknown", "iso": "unknown", "kvm": "unknown"}
        body["setup_needed"] = True

    try:
        from templeos.vm import status as vm_status

        result = vm_status()
    except NotImplementedError:
        body["setup_needed"] = body["setup_needed"] or _setup_needed(body.get("checks"), doctor_body, body.get("code"))
        body["agent_busy"] = agent_is_busy()
        return body
    except Exception as exc:
        body["ok"] = False
        body["error"] = str(exc) or "VM status failed."
        body["code"] = Code.DOCTOR_FAILED
        body["fix"] = CODE_FIX[Code.DOCTOR_FAILED]
        body["setup_needed"] = True
        return body

    body["vm_implemented"] = True
    if isinstance(result, dict):
        reserved = {"error", "code", "fix"}
        body.update({k: v for k, v in result.items() if k not in reserved})
        if "sockets" in result:
            body["sockets"] = _sanitize_sockets(result.get("sockets"))
        if result.get("ok") is False:
            # Keep a shaped status so the pane can still render onboarding.
            body["ok"] = True
            if result.get("code"):
                body["code"] = result.get("code")
                body["error"] = result.get("error")
                body["fix"] = result.get("fix")
        else:
            body["ok"] = True
            if body.get("code") not in {Code.QEMU_MISSING, Code.ISO_MISSING, Code.ISO_HASH_MISMATCH, Code.DOCTOR_FAILED}:
                body["error"] = None
                body["code"] = None
                body["fix"] = None
        if result.get("flavor"):
            _apply_flavor_dims(body, str(result.get("flavor")))
        snaps = result.get("snapshots")
        if isinstance(snaps, list):
            body["snapshots"] = [str(item) for item in snaps if isinstance(item, str)]
        elif body.get("snapshot"):
            body["snapshots"] = [str(body["snapshot"])]
        if GOLDEN not in body["snapshots"]:
            body["snapshots"] = [GOLDEN, *body["snapshots"]]
        if result.get("accel") == "kvm":
            body["kvm"] = True
        elif result.get("kvm") is True:
            body["kvm"] = True
            body.setdefault("accel", "kvm")
        if result.get("running"):
            body["running"] = True
            body["ready"] = True

    body["setup_needed"] = _setup_needed(body.get("checks"), doctor_body, body.get("code"))
    if body.get("running"):
        # A running guest means doctor already succeeded for this session.
        if body.get("code") not in {Code.QEMU_MISSING, Code.ISO_MISSING, Code.ISO_HASH_MISMATCH}:
            body["setup_needed"] = False
            body["ready"] = True
    body["agent_busy"] = agent_is_busy()
    body["sockets"] = _sanitize_sockets(body.get("sockets"))
    # Re-apply arbiter last so VM status cannot clobber control state.
    body.update(get_arbiter().snapshot())
    return body


def set_control(body: dict[str, Any] | None) -> dict[str, Any]:
    """Take control / Hand back / set mode. Fully implemented in Slice 0."""
    body = body or {}
    raw = body.get("op") or body.get("mode")
    if raw is None:
        return _json_err("Send op or mode (watch, shared, user, take, handback).", Code.INVALID_ARGS)
    token = str(raw).strip().lower().replace("-", "_")
    mapping = {
        "take": "user",
        "take_control": "user",
        "user": "user",
        "handback": "shared",
        "hand_back": "shared",
        "shared": "shared",
        "watch": "watch",
    }
    mode = mapping.get(token)
    if mode is None:
        return _json_err(
            f"Unknown control {raw!r}. Use take, handback, watch, shared, or user.",
            Code.INVALID_ARGS,
        )
    snap = get_arbiter().set_mode(mode)
    note_agent_action(
        tool="control",
        op=token,
        ok=True,
        summary=f"mode {mode}",
        source="user",
    )
    return _json_ok(**snap, agent_busy=agent_is_busy())


def user_input(body: dict[str, Any] | None) -> dict[str, Any]:
    """Record a user event (starts shared-mode hold-off) and try to inject it."""
    body = body or {}
    arbiter = get_arbiter()
    result: Any = None
    with arbiter.queue():
        snap = arbiter.note_user_input()
        if not snap["user_may_input"]:
            return _json_err(
                "The pane is in watch mode; only the agent injects input.",
                Code.WATCH_ONLY,
                mode=snap["mode"],
                agent_paused=snap["agent_paused"],
                hold_off_s=snap["hold_off_s"],
                user_may_input=False,
            )
        kind = body.get("type") or body.get("op") or "key"
        try:
            if kind in ("key", "type", "keys"):
                from templeos import input as inp

                if body.get("text"):
                    result = inp.type_text(str(body["text"]))
                elif body.get("keys"):
                    result = inp.send_keys(list(body["keys"]))
                elif body.get("key"):
                    result = inp.send_keys([str(body["key"])])
                else:
                    return _json_err("User key event needs text, key, or keys.", Code.INVALID_ARGS, **snap)
            elif kind in ("click", "pointer", "move"):
                from templeos import input as inp

                x, y = _as_int(body.get("x")), _as_int(body.get("y"))
                if x is None or y is None:
                    return _json_err("Pointer events need integer x and y.", Code.INVALID_ARGS, **snap)
                if kind == "move" or body.get("move_only"):
                    result = inp.move(x, y)
                else:
                    result = inp.click(x, y, button=str(body.get("button") or "left"))
            else:
                return _json_err(f"Unknown input type {kind!r}.", Code.INVALID_ARGS, **snap)
        except NotImplementedError as exc:
            envelope = _json_err(
                str(exc) or "User input injection is not implemented yet.",
                Code.NOT_IMPLEMENTED,
                **snap,
            )
            return envelope
    if isinstance(result, dict):
        result.setdefault("ok", True)
        if result.get("ok") is False:
            result.setdefault("fix", CODE_FIX.get(result.get("code") or "", "See docs/CONTRACTS.md."))
        result.update({k: v for k, v in snap.items() if k not in result})
        return result
    return _json_ok(**snap)


def _cap_frame(body: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    if len(text.encode("utf-8")) <= MAX_FRAME_JSON_BYTES:
        return body
    slim = _json_err(
        "Frame exceeded the 512 KiB JSON relay budget.",
        Code.PAYLOAD_TOO_LARGE,
        mime=body.get("mime") or "image/png",
        data=None,
        sha256=body.get("sha256"),
        width=body.get("width"),
        height=body.get("height"),
        unchanged=False,
    )
    return slim


def frame_payload(*, since: str | None = None) -> dict[str, Any]:
    """PNG frame for the pane (base64). Unchanged sha256/ETag skips the payload."""
    try:
        from templeos.screen import look

        result = look()
    except NotImplementedError as exc:
        return _json_err(
            str(exc) or "Frame capture is not implemented yet.",
            Code.NOT_IMPLEMENTED,
            mime="image/png",
            data=None,
            unchanged=False,
        )
    if not isinstance(result, dict):
        return _json_err("look() returned a non-object.", "internal_error", mime="image/png", data=None)
    body = dict(result)
    body.setdefault("ok", True)
    body.setdefault("mime", "image/png")
    body.setdefault("data", None)
    sha = body.get("sha256")
    tag = (since or "").strip().strip('"')
    if body.get("ok") is False:
        body.setdefault("error", "Frame capture failed.")
        body.setdefault("code", "internal_error")
        body.setdefault("fix", CODE_FIX.get(body.get("code") or "", "See docs/CONTRACTS.md."))
        body["unchanged"] = False
        if body.get("code") in SOFT_FRAME_CODES:
            body["data"] = None
        return _cap_frame(body)
    if tag and sha and tag == str(sha):
        cheap = _json_ok(
            mime=body.get("mime") or "image/png",
            data=None,
            width=body.get("width"),
            height=body.get("height"),
            sha256=str(sha),
            caption=body.get("caption"),
            unchanged=True,
        )
        return cheap
    body["ok"] = True
    body["error"] = None
    body["code"] = None
    body["fix"] = None
    body["unchanged"] = False
    return _cap_frame(body)


def vm_action(body: dict[str, Any] | None) -> dict[str, Any]:
    """Start, stop, or reset the guest via templeos.vm."""
    body = body or {}
    raw = body.get("op") or body.get("action")
    if not isinstance(raw, str) or not raw.strip():
        return _json_err("Send op: start, stop, or reset.", Code.INVALID_ARGS)
    op = raw.strip().lower()
    if op not in {"start", "stop", "reset"}:
        return _json_err(f"Unknown VM op {raw!r}. Use start, stop, or reset.", Code.INVALID_OP)
    from templeos import vm

    if op == "start":
        flavor, flavor_err = _flavor_or_err(body.get("flavor") or DEFAULT)
        if flavor_err:
            return flavor_err
        name, name_err = _snapshot_name(body.get("name") or body.get("snapshot"))
        if name_err:
            return name_err
        result = _from_impl(vm.start, flavor=flavor, snapshot=name, unit="vm.start")
    elif op == "stop":
        result = _from_impl(vm.stop, unit="vm.stop")
    else:
        result = _from_impl(vm.reset, unit="vm.reset")
    note_agent_action(tool="templeos_vm", op=op, ok=bool(result.get("ok")), code=result.get("code"), source="user")
    if result.get("ok"):
        status = status_payload()
        merged = dict(status)
        merged.update({k: v for k, v in result.items() if k not in {"error", "code", "fix"} or result.get("ok")})
        merged["ok"] = True
        merged["error"] = None
        merged["code"] = None
        merged["fix"] = None
        return merged
    return result


def snapshots_payload() -> dict[str, Any]:
    names: list[str] = [GOLDEN]
    current: Any = None
    implemented = True
    from templeos import vm

    lister = getattr(vm, "list_snapshots", None)
    raw: dict[str, Any] | None = None
    if callable(lister):
        raw = _from_impl(lister, unit="vm.list_snapshots")
        if raw.get("code") == Code.NOT_IMPLEMENTED:
            implemented = False
            raw = None
    if raw is None:
        raw = _from_impl(vm.status, unit="vm.status")
        if raw.get("code") == Code.NOT_IMPLEMENTED:
            implemented = False
    if raw and raw.get("ok") is not False:
        found = raw.get("snapshots")
        if isinstance(found, list):
            names = [str(item) for item in found if isinstance(item, str) and item]
        current = raw.get("snapshot")
    elif raw and raw.get("code") == Code.NOT_IMPLEMENTED:
        implemented = False
    elif raw and raw.get("ok") is False and raw.get("code") != Code.NOT_IMPLEMENTED:
        return raw
    if GOLDEN not in names:
        names = [GOLDEN, *names]
    return _json_ok(snapshots=names, snapshot=current, current=current, list_implemented=implemented)


def snapshot_action(body: dict[str, Any] | None) -> dict[str, Any]:
    body = body or {}
    raw = body.get("op") or body.get("action") or "list"
    if not isinstance(raw, str) or not raw.strip():
        return _json_err("Send op: list, save, or restore.", Code.INVALID_ARGS)
    op = raw.strip().lower()
    if op in {"list", "ls"}:
        return snapshots_payload()
    if op in {"save", "snapshot"}:
        op = "save"
    elif op in {"restore", "load"}:
        op = "restore"
    else:
        return _json_err(f"Unknown snapshot op {raw!r}. Use list, save, or restore.", Code.INVALID_OP)
    name, name_err = _snapshot_name(body.get("name") or body.get("snapshot"))
    if name_err:
        return name_err
    from templeos import vm

    if op == "save":
        result = _from_impl(vm.snapshot, name, unit="vm.snapshot")
    else:
        result = _from_impl(vm.restore, name, unit="vm.restore")
    note_agent_action(
        tool="templeos_vm",
        op="snapshot" if op == "save" else "restore",
        ok=bool(result.get("ok")),
        code=result.get("code"),
        summary=f"{op} {name}",
        source="user",
    )
    if result.get("ok"):
        status = status_payload()
        status["snapshot"] = result.get("snapshot") or name
        return status
    return result


def setup_payload(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch the pinned ISO and run doctor. The pane's Set up button calls this."""
    body = body or {}
    flavor, flavor_err = _flavor_or_err(body.get("flavor") or DEFAULT)
    if flavor_err:
        return flavor_err
    from templeos import doctor as doctor_mod

    iso = _from_impl(doctor_mod.ensure_iso, flavor, unit="doctor.ensure_iso")
    report = _from_impl(doctor_mod.doctor, unit="doctor")
    note_agent_action(
        tool="templeos_vm",
        op="doctor",
        ok=bool(iso.get("ok") and report.get("ok") or report.get("code") != Code.NOT_IMPLEMENTED and iso.get("ok")),
        code=iso.get("code") or report.get("code"),
        summary="setup",
        source="user",
    )
    if iso.get("code") == Code.NOT_IMPLEMENTED and report.get("code") == Code.NOT_IMPLEMENTED:
        return _json_err(
            "Doctor setup is contracted but not implemented yet.",
            Code.NOT_IMPLEMENTED,
            flavor=flavor,
            setup_needed=True,
        )
    if iso.get("ok") is False and iso.get("code") != Code.NOT_IMPLEMENTED:
        iso["setup_needed"] = True
        iso["flavor"] = flavor
        iso["doctor"] = report
        return iso
    if report.get("ok") is False and report.get("code") != Code.NOT_IMPLEMENTED:
        report["setup_needed"] = True
        report["flavor"] = flavor
        report["iso"] = iso
        return report
    status = status_payload()
    status["setup"] = {"iso": iso, "doctor": report}
    return status


def log_payload(*, limit: int | None = None) -> dict[str, Any]:
    events = activity_events(limit=limit)
    return _json_ok(events=events, count=len(events), agent_busy=agent_is_busy())


def _json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("Send a JSON object.") from exc
    if not isinstance(data, dict):
        raise ValueError("Send a JSON object.")
    return data


def _frame_since(request: Any) -> str | None:
    if request is None:
        return None
    query = getattr(request, "query_params", None)
    since = None
    if query is not None:
        since = query.get("since") or query.get("etag") or query.get("hash")
    headers = getattr(request, "headers", None)
    if not since and headers is not None:
        since = headers.get("if-none-match") or headers.get("If-None-Match")
    if not since:
        return None
    return str(since).strip().strip('"')


def create_router():
    """Build the FastAPI router. Requires fastapi (provided by Hermes, or dev extra)."""
    if APIRouter is None or Request is None:
        raise ImportError("fastapi is required to mount TempleOS pane routes")

    router = APIRouter()

    @router.get("/health")
    def route_health():
        return health_payload()

    @router.get("/status")
    def route_status():
        return status_payload()

    @router.get("/frame")
    def route_frame(request: Request):
        return frame_payload(since=_frame_since(request))

    @router.get("/control")
    def route_control_get():
        snap = get_arbiter().snapshot()
        return _json_ok(**snap, agent_busy=agent_is_busy())

    @router.post("/control")
    async def route_control(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        return set_control(body)

    @router.post("/input")
    async def route_input(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        return user_input(body)

    @router.post("/vm")
    async def route_vm(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        return vm_action(body)

    @router.post("/start")
    async def route_start(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        body["op"] = "start"
        return vm_action(body)

    @router.post("/stop")
    async def route_stop():
        return vm_action({"op": "stop"})

    @router.post("/reset")
    async def route_reset():
        return vm_action({"op": "reset"})

    @router.get("/snapshots")
    def route_snapshots_get():
        return snapshots_payload()

    @router.post("/snapshots")
    async def route_snapshots(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        return snapshot_action(body)

    @router.get("/log")
    def route_log(request: Request):
        raw = request.query_params.get("limit") if request.query_params is not None else None
        limit = None
        if raw:
            try:
                limit = int(raw)
            except ValueError:
                return _json_err("limit must be an integer.", Code.INVALID_ARGS)
        return log_payload(limit=limit)

    @router.get("/doctor")
    def route_doctor():
        return _doctor_report()

    @router.post("/setup")
    async def route_setup(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return _json_err(str(exc), Code.INVALID_ARGS)
        return setup_payload(body)

    return router


try:
    router = create_router()
except ImportError:  # pragma: no cover - fastapi is optional outside Hermes
    router = None
