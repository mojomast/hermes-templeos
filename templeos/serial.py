"""COM1 unix-socket reader/writer.

Slice A (feat/vm) implements this module. The backend must keep COM1 open for
the whole session: a reader that is not already connected misses guest bytes.
"""

from __future__ import annotations

from pathlib import Path


class SerialPort:
    """Persistent COM1 connection (unix socket, server already listening)."""

    def __init__(self) -> None:
        self.path: Path | None = None
        self.connected: bool = False

    def open(self, path: Path, *, timeout_s: float = 5.0) -> None:
        """Connect and leave the socket open."""
        raise NotImplementedError("templeos.serial.SerialPort.open: Slice A (feat/vm)")

    def close(self) -> None:
        """Close the socket. Idempotent."""
        raise NotImplementedError("templeos.serial.SerialPort.close: Slice A (feat/vm)")

    def write(self, data: bytes) -> int:
        """Send bytes to the guest. Raises if the port is not open."""
        raise NotImplementedError("templeos.serial.SerialPort.write: Slice A (feat/vm)")

    def read(self, n: int = 4096, *, timeout_s: float = 0.2) -> bytes:
        """Read up to n bytes, or b'' on timeout."""
        raise NotImplementedError("templeos.serial.SerialPort.read: Slice A (feat/vm)")

    def read_available(self) -> bytes:
        """Drain whatever is already buffered without a long wait."""
        raise NotImplementedError("templeos.serial.SerialPort.read_available: Slice A (feat/vm)")
