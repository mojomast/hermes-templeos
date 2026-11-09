"""COM1 unix-socket reader/writer.

The backend must keep COM1 open for the whole session: a reader that is not
already connected misses guest bytes. A background thread drains the socket
into a ring buffer so callers can read, read_available, or read_until without
losing data that arrived between calls.
"""

from __future__ import annotations

import socket
import threading
import time
from collections import deque
from pathlib import Path

# Keep a modest ring so a noisy guest cannot grow host memory without bound.
_RING_MAX = 1 * 1024 * 1024


class SerialError(RuntimeError):
    """The COM1 unix socket is not open, or the connection failed."""


class SerialPort:
    """Persistent COM1 connection (unix socket, server already listening)."""

    def __init__(self, *, ring_max: int = _RING_MAX) -> None:
        self.path: Path | None = None
        self.connected: bool = False
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._ring: deque[int] = deque()
        self._ring_max = max(1, int(ring_max))
        self._dropped = 0

    def open(self, path: Path, *, timeout_s: float = 5.0) -> None:
        """Connect and leave the socket open."""
        self.close()
        self.path = Path(path)
        sock = self._connect(self.path, timeout_s)
        sock.settimeout(0.2)
        self._sock = sock
        self._stop.clear()
        self.connected = True
        self._thread = threading.Thread(target=self._reader, name="templeos-com1", daemon=True)
        self._thread.start()

    def close(self) -> None:
        """Close the socket. Idempotent."""
        self._stop.set()
        self.connected = False
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    def write(self, data: bytes) -> int:
        """Send bytes to the guest. Raises if the port is not open."""
        if not self.connected or self._sock is None:
            raise SerialError("serial not open")
        self._sock.sendall(data)
        return len(data)

    def read(self, n: int = 4096, *, timeout_s: float = 0.2) -> bytes:
        """Read up to n bytes, or b'' on timeout."""
        if not self.connected:
            raise SerialError("serial not open")
        if n <= 0:
            return b""
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._cond:
            while len(self._ring) == 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b""
                self._cond.wait(remaining)
            return self._take(n)

    def read_available(self) -> bytes:
        """Drain whatever is already buffered without a long wait."""
        if not self.connected:
            raise SerialError("serial not open")
        with self._lock:
            return self._take(len(self._ring))

    def read_until(
        self,
        marker: bytes,
        *,
        timeout_s: float = 5.0,
        max_bytes: int = 64 * 1024,
    ) -> bytes:
        """Block until ``marker`` appears in the stream, or raise TimeoutError.

        Returns the bytes up to and including the first occurrence of ``marker``.
        """
        if not self.connected:
            raise SerialError("serial not open")
        if not marker:
            raise ValueError("read_until marker must be non-empty")
        deadline = time.monotonic() + max(0.0, timeout_s)
        collected = bytearray()
        with self._cond:
            while True:
                if self._ring:
                    collected.extend(self._take(min(len(self._ring), max_bytes - len(collected) + len(marker))))
                    idx = collected.find(marker)
                    if idx >= 0:
                        end = idx + len(marker)
                        extra = bytes(collected[end:])
                        if extra:
                            # Put leftover bytes back at the front of the ring.
                            self._ring.extendleft(reversed(extra))
                        return bytes(collected[:end])
                    if len(collected) >= max_bytes:
                        raise SerialError(f"read_until exceeded {max_bytes} bytes without seeing the marker")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # Keep what we saw in the ring so a later read can use it.
                    if collected:
                        self._ring.extendleft(reversed(collected))
                        while len(self._ring) > self._ring_max:
                            self._ring.pop()
                            self._dropped += 1
                    raise TimeoutError("serial read_until timed out")
                self._cond.wait(remaining)

    @property
    def dropped(self) -> int:
        """Count of oldest bytes discarded when the ring was full."""
        return self._dropped

    def _connect(self, path: Path, timeout_s: float) -> socket.socket:
        deadline = time.monotonic() + timeout_s
        last: OSError | None = None
        while time.monotonic() < deadline:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                sock.connect(str(path))
                return sock
            except OSError as exc:
                last = exc
                sock.close()
                time.sleep(0.05)
        raise SerialError(f"serial connect failed: {path}: {last}")

    def _reader(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                self.connected = False
                return
            if not chunk:
                self.connected = False
                return
            with self._cond:
                for byte in chunk:
                    if len(self._ring) >= self._ring_max:
                        self._ring.popleft()
                        self._dropped += 1
                    self._ring.append(byte)
                self._cond.notify_all()

    def _take(self, n: int) -> bytes:
        out = bytearray()
        while self._ring and len(out) < n:
            out.append(self._ring.popleft())
        return bytes(out)
