"""In-process fakes for QMP, serial, and Hermes ctx. Owned by feat/integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# 1x1 PNG (black). Enough for screendump tests without Pillow.
MIN_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\xa0\r"
    b"\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


class FakeQMP:
    """Records QMP commands and can simulate bake-off pitfalls."""

    def __init__(self, *, abs_mouse: bool = True, floppy_writable: bool = False) -> None:
        self.path: Path | None = None
        self.connected = False
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.hmp_lines: list[str] = []
        self.events: list[list[dict[str, Any]]] = []
        self.keys: list[list[str]] = []
        self.running = True
        self.paused = False
        self.abs_mouse = abs_mouse
        self.floppy_writable = floppy_writable
        self.fail_loadvm = False
        self.snapshots: set[str] = set()
        self.framebuffer = MIN_PNG

    def connect(self, path: Path, *, timeout_s: float = 30.0) -> None:
        self.path = Path(path)
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def cmd(self, execute: str, **arguments: Any) -> dict[str, Any]:
        if not self.connected:
            raise RuntimeError("QMP is not connected")
        self.commands.append((execute, arguments))
        if execute == "screendump":
            dest = Path(arguments["filename"])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.framebuffer)
            return {"return": {}}
        if execute == "send-key":
            codes = [item.get("data") for item in arguments.get("keys", [])]
            self.keys.append([c for c in codes if c])
            return {"return": {}}
        if execute == "input-send-event":
            events = list(arguments.get("events") or [])
            if not self.abs_mouse and any(_is_abs(ev) for ev in events):
                raise RuntimeError("input handler not found for event type abs")
            self.events.append(events)
            return {"return": {}}
        if execute == "human-monitor-command":
            return {"return": self._hmp(str(arguments.get("command-line") or ""))}
        if execute == "qmp_capabilities":
            return {"return": {}}
        return {"return": {}}

    def hmp(self, command: str) -> str:
        return str(self.cmd("human-monitor-command", **{"command-line": command}).get("return", ""))

    def _hmp(self, command: str) -> str:
        self.hmp_lines.append(command)
        if command.startswith("savevm"):
            if self.floppy_writable:
                raise RuntimeError("Device 'floppy0' does not support snapshots")
            name = command.split(None, 1)[1].strip() if " " in command else "golden"
            self.snapshots.add(name)
            return ""
        if command.startswith("loadvm"):
            if self.fail_loadvm:
                self.paused = True
                raise RuntimeError("loadvm failed")
            self.paused = True
            name = command.split(None, 1)[1].strip() if " " in command else "golden"
            self.snapshots.add(name)
            return ""
        if command.strip() == "cont":
            self.paused = False
            return ""
        if command.startswith("eject"):
            self.floppy_writable = False
            return ""
        return ""

    def screendump(self, dest: Path, fmt: str = "png") -> Path:
        self.cmd("screendump", filename=str(dest), format=fmt)
        return dest

    def send_key(self, codes: list[str], *, hold_ms: int = 80) -> None:
        keys = [{"type": "qcode", "data": c} for c in codes]
        self.cmd("send-key", keys=keys, **{"hold-time": hold_ms})

    def input_send_event(self, events: list[dict[str, Any]]) -> None:
        self.cmd("input-send-event", events=events)


def _is_abs(event: dict[str, Any]) -> bool:
    if event.get("type") == "abs":
        return True
    data = event.get("data") or event.get("abs") or {}
    axis = str(data.get("axis") or event.get("axis") or "")
    return "abs" in json.dumps(event) and axis.startswith("x") or event.get("kind") == "abs"


class FakeSerial:
    """Guest bytes are lost unless the host already called open()."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.connected = False
        self.rx = bytearray()
        self.tx = bytearray()
        self.dropped = bytearray()

    def open(self, path: Path, *, timeout_s: float = 5.0) -> None:
        self.path = Path(path)
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def write(self, data: bytes) -> int:
        if not self.connected:
            raise RuntimeError("serial not open")
        self.tx.extend(data)
        return len(data)

    def read(self, n: int = 4096, *, timeout_s: float = 0.2) -> bytes:
        if not self.connected:
            raise RuntimeError("serial not open")
        chunk = bytes(self.rx[:n])
        del self.rx[:n]
        return chunk

    def read_available(self) -> bytes:
        return self.read(len(self.rx), timeout_s=0)

    def guest_write(self, data: bytes) -> None:
        """Simulate the guest writing to COM1."""
        if self.connected:
            self.rx.extend(data)
        else:
            self.dropped.extend(data)


class FakeCtx:
    """Records register_tool / register_skill the way Hermes would."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}
        self.schemas: dict[str, dict[str, Any]] = {}
        self.skills: dict[str, Path] = {}
        self.hooks: dict[str, Any] = {}

    def register_tool(
        self,
        name,
        toolset,
        schema,
        handler,
        check_fn=None,
        requires_env=None,
        is_async=False,
        description="",
        emoji="",
        override=False,
    ):
        assert schema["name"] == name
        assert schema["parameters"]["type"] == "object"
        self.tools[name] = handler
        self.schemas[name] = schema

    def register_skill(self, name, path):
        self.skills[name] = Path(path)

    def register_hook(self, name, fn):
        self.hooks[name] = fn
