from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import pytest

from templeos.serial import SerialError, SerialPort


class SerialServer:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.unlink(missing_ok=True)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        self._sock.listen(1)
        self._sock.settimeout(0.3)
        self.conn: socket.socket | None = None
        self.rx = bytearray()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, name="serial-stub", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        if self.conn is not None:
            try:
                self.conn.close()
            except OSError:
                pass
        self.thread.join(timeout=2.0)
        self.path.unlink(missing_ok=True)

    def wait_client(self, timeout: float = 5.0) -> socket.socket:
        if not self._ready.wait(timeout):
            raise TimeoutError("serial stub did not accept a client")
        assert self.conn is not None
        return self.conn

    def guest_write(self, data: bytes) -> None:
        conn = self.wait_client()
        conn.sendall(data)

    def guest_read(self, n: int = 4096, timeout: float = 2.0) -> bytes:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.rx:
                chunk = bytes(self.rx[:n])
                del self.rx[:n]
                return chunk
            time.sleep(0.02)
        return b""

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.conn = conn
            self._ready.set()
            conn.settimeout(0.3)
            try:
                while not self._stop.is_set():
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        return
                    if not chunk:
                        return
                    self.rx.extend(chunk)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass


@pytest.fixture
def serial_server(tmp_path):
    server = SerialServer(tmp_path / "com1.sock")
    yield server
    server.close()


def test_open_write_read_and_available(serial_server):
    port = SerialPort()
    with pytest.raises(SerialError):
        port.write(b"A")
    port.open(serial_server.path, timeout_s=5)
    try:
        assert port.connected is True
        assert port.write(b"hello") == 5
        assert serial_server.guest_read() == b"hello"
        serial_server.guest_write(b"AZXYZ")
        # Wait until the reader thread has buffered the guest bytes.
        deadline = time.monotonic() + 2
        data = b""
        while time.monotonic() < deadline and data != b"AZXYZ":
            data += port.read(5, timeout_s=0.2)
        assert data == b"AZXYZ"
        serial_server.guest_write(b"more")
        time.sleep(0.15)
        assert port.read_available() == b"more"
        assert port.read_available() == b""
    finally:
        port.close()
        port.close()
        assert port.connected is False


def test_read_until_and_ring_overflow(serial_server):
    port = SerialPort(ring_max=16)
    port.open(serial_server.path, timeout_s=5)
    try:
        serial_server.guest_write(b"hello\nworld")
        assert port.read_until(b"\n", timeout_s=2) == b"hello\n"
        assert port.read_available() == b"world"
        serial_server.guest_write(b"0123456789abcdefghij")
        time.sleep(0.2)
        available = port.read_available()
        assert len(available) == 16
        assert port.dropped >= 4
        assert available.endswith(b"j")
        with pytest.raises(TimeoutError):
            port.read_until(b"NEVER", timeout_s=0.2)
    finally:
        port.close()


def test_connect_fails_on_missing_socket(tmp_path):
    port = SerialPort()
    with pytest.raises(SerialError, match="connect failed"):
        port.open(tmp_path / "missing.sock", timeout_s=0.3)
