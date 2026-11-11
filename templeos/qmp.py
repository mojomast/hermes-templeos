"""QMP client over a unix socket.

Talk JSON lines, skip event objects, and call qmp_capabilities after the
greeting. Commands are QMP, not a shell. A background reader thread collects
events and matches replies (by id, with a FIFO fallback) so execute() can
wait with a timeout. reconnect() re-negotiates capabilities on the same path.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


class QMPError(RuntimeError):
    """A QMP command returned an error object, or the socket failed."""

    def __init__(self, message: str, *, transport: bool = False) -> None:
        super().__init__(message)
        self.transport = transport


class QMPClient:
    """One connection to QEMU's QMP unix socket.

    Threaded, not asyncio: tool handlers are synchronous. The reader loop
    skips ``event`` objects when matching command replies and stores them
    on a ring so callers can inspect recent events.
    """

    def __init__(self) -> None:
        self.path: Path | None = None
        self.command_timeout_s: float = 30.0
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._buf = b""
        self._next_id = 1
        self._pending: dict[int, dict[str, Any] | None] = {}
        self._fifo: deque[int] = deque()
        self._events: deque[dict[str, Any]] = deque(maxlen=256)
        self._greeting: dict[str, Any] | None = None
        self._connected = False
        self._reader_error: BaseException | None = None

    @property
    def connected(self) -> bool:
        return self._connected and self._sock is not None

    def connect(self, path: Path, *, timeout_s: float = 30.0) -> None:
        """Connect, read the greeting, and negotiate capabilities."""
        self.close()
        self.path = Path(path)
        self._open_socket(timeout_s)
        self._start_reader()
        self._wait_greeting(timeout_s)
        self.cmd("qmp_capabilities", timeout_s=min(timeout_s, 10.0))
        self._connected = True

    def reconnect(self, *, timeout_s: float = 30.0) -> None:
        """Drop the current socket, connect again, and re-negotiate capabilities."""
        if self.path is None:
            raise QMPError("QMP reconnect needs a path; call connect() first")
        path = self.path
        self._teardown(clear_path=False)
        self.path = path
        self._open_socket(timeout_s)
        self._start_reader()
        self._wait_greeting(timeout_s)
        self.cmd("qmp_capabilities", timeout_s=min(timeout_s, 10.0))
        self._connected = True

    def close(self) -> None:
        """Close the socket. Idempotent."""
        self._teardown(clear_path=False)

    def cmd(self, execute: str, **arguments: Any) -> dict[str, Any]:
        """Send a QMP command and return the response object (events skipped).

        ``timeout_s`` is a client option and is not forwarded to QEMU. On a
        broken pipe the client reconnects once and retries the command.
        """
        timeout_s = arguments.pop("timeout_s", None)
        if timeout_s is None:
            timeout_s = self.command_timeout_s
        try:
            return self._execute(execute, arguments, float(timeout_s))
        except QMPError as exc:
            if not exc.transport or not self.path or execute == "qmp_capabilities":
                raise
            return self._retry_after_disconnect(execute, arguments, float(timeout_s), exc)
        except (BrokenPipeError, ConnectionError, OSError) as exc:
            if not self.path or execute == "qmp_capabilities":
                raise
            return self._retry_after_disconnect(execute, arguments, float(timeout_s), exc)

    def hmp(self, command: str) -> str:
        """human-monitor-command wrapper. Used for savevm/loadvm/eject/cont."""
        resp = self.cmd("human-monitor-command", **{"command-line": command})
        ret = resp.get("return", "")
        if ret is None or ret == {} or ret == []:
            return ""
        return ret if isinstance(ret, str) else str(ret)

    def screendump(self, dest: Path, fmt: str = "png") -> Path:
        """Write a frame via QMP screendump. Prefer PNG."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        args: dict[str, Any] = {"filename": str(dest)}
        if fmt:
            args["format"] = fmt
        self.cmd("screendump", **args)
        return dest

    def send_key(self, codes: list[str], *, hold_ms: int = 80) -> None:
        """QMP send-key with qcode names."""
        keys = [{"type": "qcode", "data": c} for c in codes]
        self.cmd("send-key", keys=keys, **{"hold-time": int(hold_ms)})

    def input_send_event(self, events: list[dict[str, Any]]) -> None:
        """QMP input-send-event (absolute, relative, or button)."""
        self.cmd("input-send-event", events=events)

    def events(self) -> list[dict[str, Any]]:
        """Copy of recent QMP events (does not clear the ring)."""
        with self._lock:
            return list(self._events)

    def pop_events(self) -> list[dict[str, Any]]:
        """Return and clear the event ring."""
        with self._lock:
            out = list(self._events)
            self._events.clear()
            return out

    def greeting(self) -> dict[str, Any] | None:
        """The QMP greeting object, if one has been received."""
        return self._greeting

    # --- internals ---

    def _retry_after_disconnect(
        self,
        execute: str,
        arguments: dict[str, Any],
        timeout_s: float,
        exc: BaseException,
    ) -> dict[str, Any]:
        try:
            self.reconnect(timeout_s=min(timeout_s, 15.0))
        except Exception as retry_exc:
            raise QMPError(
                f"QMP reconnect failed after {execute} error: {retry_exc}",
                transport=True,
            ) from exc
        return self._execute(execute, arguments, timeout_s)

    def _execute(self, execute: str, arguments: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        if self._sock is None:
            raise QMPError("QMP is not connected", transport=True)
        with self._lock:
            ident = self._next_id
            self._next_id += 1
            self._pending[ident] = None
            self._fifo.append(ident)
        payload: dict[str, Any] = {"execute": execute, "id": ident}
        if arguments:
            payload["arguments"] = arguments
        raw = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self._sock.sendall(raw)
        except OSError:
            with self._lock:
                self._pending.pop(ident, None)
                try:
                    self._fifo.remove(ident)
                except ValueError:
                    pass
            raise
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while True:
                reply = self._pending.get(ident)
                if reply is not None:
                    self._pending.pop(ident, None)
                    break
                if self._reader_error is not None:
                    err = self._reader_error
                    self._pending.pop(ident, None)
                    raise QMPError(f"QMP reader failed during {execute}: {err}", transport=True) from err
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._pending.pop(ident, None)
                    try:
                        self._fifo.remove(ident)
                    except ValueError:
                        pass
                    raise TimeoutError(f"QMP {execute} timed out after {timeout_s}s")
                self._cond.wait(remaining)
        if "error" in reply:
            err = reply["error"]
            desc = err.get("desc") if isinstance(err, dict) else err
            raise QMPError(f"QMP {execute} error: {desc}")
        return reply

    def _open_socket(self, timeout_s: float) -> None:
        if self.path is None:
            raise QMPError("QMP connect needs a path")
        deadline = time.monotonic() + timeout_s
        last: OSError | None = None
        while time.monotonic() < deadline:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                sock.connect(str(self.path))
            except OSError as exc:
                last = exc
                sock.close()
                time.sleep(0.05)
                continue
            self._sock = sock
            return
        raise QMPError(f"QMP connect failed: {self.path}: {last}")

    def _start_reader(self) -> None:
        self._stop.clear()
        self._reader_error = None
        self._buf = b""
        self._thread = threading.Thread(target=self._reader, name="templeos-qmp", daemon=True)
        self._thread.start()

    def _wait_greeting(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while self._greeting is None:
                if self._reader_error is not None:
                    raise QMPError(f"QMP greeting failed: {self._reader_error}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise QMPError(f"QMP greeting timed out after {timeout_s}s")
                self._cond.wait(remaining)

    def _reader(self) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            while not self._stop.is_set():
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                except OSError as exc:
                    self._fail_reader(exc)
                    return
                if not chunk:
                    self._fail_reader(ConnectionError("QMP socket closed"))
                    return
                self._buf += chunk
                while b"\n" in self._buf:
                    line, self._buf = self._buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    if isinstance(obj, dict):
                        self._dispatch(obj)
        except Exception as exc:  # pragma: no cover - defensive
            self._fail_reader(exc)

    def _dispatch(self, obj: dict[str, Any]) -> None:
        with self._cond:
            if "QMP" in obj and "return" not in obj and "error" not in obj:
                self._greeting = obj
                self._cond.notify_all()
                return
            if "event" in obj and "return" not in obj and "error" not in obj:
                self._events.append(obj)
                self._cond.notify_all()
                return
            ident = obj.get("id")
            if ident is None and self._fifo:
                ident = self._fifo.popleft()
            elif ident in self._pending:
                try:
                    self._fifo.remove(ident)
                except ValueError:
                    pass
            if ident in self._pending:
                self._pending[ident] = obj
            self._cond.notify_all()

    def _fail_reader(self, exc: BaseException) -> None:
        with self._cond:
            self._reader_error = exc
            self._connected = False
            self._cond.notify_all()

    def _teardown(self, *, clear_path: bool) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        self._connected = False
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
        with self._lock:
            self._pending.clear()
            self._fifo.clear()
            self._buf = b""
            self._greeting = None
            self._reader_error = None
        if clear_path:
            self.path = None
