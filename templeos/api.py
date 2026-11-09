"""Backend routes for the Desktop pane.

Mounted at /api/plugins/templeos/ (see dashboard/plugin_api.py). The pane
calls these only through ctx.rest. This process is the only one that opens
QEMU unix sockets. Never print tokens; there is no sidecar token for the
iframe to read.

Slice C (feat/pane) fills in frame streaming and live input against a running
VM. Control mode and health already work because the arbiter is concrete.
"""

from __future__ import annotations

import json
from typing import Any

from templeos import PLUGIN_ID, __version__
from templeos.arbiter import get_arbiter
from templeos.tools import CODE_FIX, Code, err

try:
    from fastapi import APIRouter, Request
except ImportError:  # pragma: no cover - fastapi is optional outside Hermes
    APIRouter = None
    Request = None

# Whole serialized JSON (base64 + envelope) must stay under this budget.
MAX_FRAME_JSON_BYTES = 512 * 1024

ROUTE_HEALTH = "/health"
ROUTE_STATUS = "/status"
ROUTE_FRAME = "/frame"
ROUTE_INPUT = "/input"
ROUTE_CONTROL = "/control"


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
    }


def status_payload() -> dict[str, Any]:
    """Arbiter fields always; VM fields from templeos.vm.status when implemented."""
    snap = get_arbiter().snapshot()
    body: dict[str, Any] = {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        "plugin": PLUGIN_ID,
        "version": __version__,
        "running": False,
        "flavor": "tinkeros",
        "accel": None,
        "snapshot": None,
        "kvm": False,
        "sockets": {"qmp": False, "vnc": False, "com1": False},
        **snap,
    }
    try:
        from templeos.vm import status as vm_status

        result = vm_status()
    except NotImplementedError:
        body["ok"] = False
        body["error"] = "VM status is contracted but not implemented yet."
        body["code"] = Code.NOT_IMPLEMENTED
        body["fix"] = CODE_FIX[Code.NOT_IMPLEMENTED]
        return body
    except Exception as exc:
        body["ok"] = False
        body["error"] = str(exc) or "VM status failed."
        body["code"] = Code.DOCTOR_FAILED
        body["fix"] = CODE_FIX[Code.DOCTOR_FAILED]
        return body
    if isinstance(result, dict):
        body.update({k: v for k, v in result.items() if k not in {"error", "code", "fix"}})
        if result.get("ok") is False:
            body["ok"] = False
            body["error"] = result.get("error")
            body["code"] = result.get("code")
            body["fix"] = result.get("fix")
        else:
            body["ok"] = True
            body["error"] = None
            body["code"] = None
            body["fix"] = None
    return body


def set_control(body: dict[str, Any] | None) -> dict[str, Any]:
    """Take control / Hand back / set mode. Fully implemented in Slice 0."""
    body = body or {}
    raw = body.get("op") or body.get("mode")
    if raw is None:
        return json.loads(err("Send op or mode (watch, shared, user, take, handback).", Code.INVALID_ARGS))
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
        return json.loads(
            err(
                f"Unknown control {raw!r}. Use take, handback, watch, shared, or user.",
                Code.INVALID_ARGS,
            )
        )
    snap = get_arbiter().set_mode(mode)
    return {
        "ok": True,
        "error": None,
        "code": None,
        "fix": None,
        **snap,
    }


def user_input(body: dict[str, Any] | None) -> dict[str, Any]:
    """Record a user event (starts shared-mode hold-off) and try to inject it."""
    body = body or {}
    arbiter = get_arbiter()
    with arbiter.queue():
        snap = arbiter.note_user_input()
        if not snap["user_may_input"]:
            return json.loads(
                err(
                    "The pane is in watch mode; only the agent injects input.",
                    Code.WATCH_ONLY,
                    mode=snap["mode"],
                )
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
                    return json.loads(err("User key event needs text, key, or keys.", Code.INVALID_ARGS))
            elif kind in ("click", "pointer", "move"):
                from templeos import input as inp

                x, y = body.get("x"), body.get("y")
                if not isinstance(x, int) or not isinstance(y, int):
                    return json.loads(err("Pointer events need integer x and y.", Code.INVALID_ARGS))
                if kind == "move" or body.get("move_only"):
                    result = inp.move(x, y)
                else:
                    result = inp.click(x, y, button=str(body.get("button") or "left"))
            else:
                return json.loads(err(f"Unknown input type {kind!r}.", Code.INVALID_ARGS))
        except NotImplementedError as exc:
            return json.loads(err(str(exc) or "User input injection is not implemented yet.", Code.NOT_IMPLEMENTED, **snap))
    if isinstance(result, dict):
        result.setdefault("ok", True)
        result.update({k: v for k, v in snap.items() if k not in result})
        return result
    return {"ok": True, "error": None, "code": None, "fix": None, **snap}


def frame_payload() -> dict[str, Any]:
    """PNG frame for the pane (base64). Slice B/C implement the dump."""
    try:
        from templeos.screen import look

        result = look()
    except NotImplementedError as exc:
        return json.loads(err(str(exc) or "Frame capture is not implemented yet.", Code.NOT_IMPLEMENTED, mime="image/png", data=None))
    if isinstance(result, dict):
        return {**result, "ok": result.get("ok", True)}
    return json.loads(err("look() returned a non-object.", "internal_error"))


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
    def route_frame():
        return frame_payload()

    @router.get("/control")
    def route_control_get():
        snap = get_arbiter().snapshot()
        return {"ok": True, "error": None, "code": None, "fix": None, **snap}

    @router.post("/control")
    async def route_control(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return json.loads(err(str(exc), Code.INVALID_ARGS))
        return set_control(body)

    @router.post("/input")
    async def route_input(request: Request):
        try:
            body = _json_body(await request.body())
        except ValueError as exc:
            return json.loads(err(str(exc), Code.INVALID_ARGS))
        return user_input(body)

    return router


try:
    router = create_router()
except ImportError:  # pragma: no cover - fastapi is optional outside Hermes
    router = None
