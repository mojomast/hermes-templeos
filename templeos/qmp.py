"""QMP client over a unix socket.

Slice A (feat/vm) implements this module. Talk JSON lines, skip event objects,
and call qmp_capabilities after the greeting. Keep commands as QMP, not a shell.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class QMPClient:
    """One connection to QEMU's QMP unix socket."""

    def __init__(self) -> None:
        self.path: Path | None = None

    def connect(self, path: Path, *, timeout_s: float = 30.0) -> None:
        """Connect, read the greeting, and negotiate capabilities."""
        raise NotImplementedError("templeos.qmp.QMPClient.connect: Slice A (feat/vm)")

    def close(self) -> None:
        """Close the socket. Idempotent."""
        raise NotImplementedError("templeos.qmp.QMPClient.close: Slice A (feat/vm)")

    def cmd(self, execute: str, **arguments: Any) -> dict[str, Any]:
        """Send a QMP command and return the response object (events skipped)."""
        raise NotImplementedError("templeos.qmp.QMPClient.cmd: Slice A (feat/vm)")

    def hmp(self, command: str) -> str:
        """human-monitor-command wrapper. Used for savevm/loadvm/eject/cont."""
        raise NotImplementedError("templeos.qmp.QMPClient.hmp: Slice A (feat/vm)")

    def screendump(self, dest: Path, fmt: str = "png") -> Path:
        """Write a frame via QMP screendump. Prefer PNG."""
        raise NotImplementedError("templeos.qmp.QMPClient.screendump: Slice A (feat/vm)")

    def send_key(self, codes: list[str], *, hold_ms: int = 80) -> None:
        """QMP send-key with qcode names."""
        raise NotImplementedError("templeos.qmp.QMPClient.send_key: Slice A (feat/vm)")

    def input_send_event(self, events: list[dict[str, Any]]) -> None:
        """QMP input-send-event (absolute, relative, or button)."""
        raise NotImplementedError("templeos.qmp.QMPClient.input_send_event: Slice A (feat/vm)")
