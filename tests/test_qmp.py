from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path

import pytest

from templeos.qmp import QMPClient, QMPError
from tests.fakes import MIN_PNG


class QMPServer:
    """Minimal JSON-line QMP unix server for protocol tests."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.unlink(missing_ok=True)
        self.commands: list[dict] = []
        self.hang_on: str | None = None
        self.events_before: list[dict] = []
        self.error_on: dict[str, dict] = {}
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(self.path))
        self._sock.listen(4)
        self._sock.settimeout(0.3)
        self._conns: list[socket.socket] = []
        self._accepted = threading.Event()
        self.thread = threading.Thread(target=self._run, name="qmp-stub", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        for conn in list(self._conns):
            try:
                conn.close()
            except OSError:
                pass
        self.thread.join(timeout=2.0)
        self.path.unlink(missing_ok=True)

    def drop_clients(self) -> None:
        for conn in list(self._conns):
            try:
                conn.close()
            except OSError:
                pass
        self._conns.clear()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self._conns.append(conn)
            self._accepted.set()
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _session(self, conn: socket.socket) -> None:
        conn.settimeout(0.3)
        greeting = {
            "QMP": {
                "version": {"qemu": {"major": 10, "minor": 0, "micro": 13}, "package": "stub"},
                "capabilities": [],
            }
        }
        try:
            conn.sendall((json.dumps(greeting) + "\n").encode())
            buf = b""
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(65536)
                except socket.timeout:
                    continue
                except OSError:
                    return
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode())
                    except ValueError:
                        continue
                    self._handle(conn, msg)
        except OSError:
            return

    def _handle(self, conn: socket.socket, msg: dict) -> None:
        self.commands.append(msg)
        execute = str(msg.get("execute") or "")
        ident = msg.get("id")
        if self.hang_on and execute == self.hang_on:
            time.sleep(30)
            return
        for event in self.events_before:
            try:
                conn.sendall((json.dumps(event) + "\n").encode())
            except OSError:
                return
        if execute == "screendump":
            filename = (msg.get("arguments") or {}).get("filename")
            if filename:
                dest = Path(filename)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(MIN_PNG)
        if execute in self.error_on:
            payload = {"error": self.error_on[execute], "id": ident}
        else:
            payload = {"return": {}, "id": ident}
        try:
            conn.sendall((json.dumps(payload) + "\n").encode())
        except OSError:
            return


@pytest.fixture
def qmp_server(tmp_path):
    server = QMPServer(tmp_path / "qmp.sock")
    yield server
    server.close()


def test_connect_greeting_capabilities_and_cmd(qmp_server, tmp_path):
    client = QMPClient()
    client.connect(qmp_server.path, timeout_s=5)
    try:
        greeting = client.greeting()
        assert greeting is not None and "QMP" in greeting
        executed = [c["execute"] for c in qmp_server.commands]
        assert executed[0] == "qmp_capabilities"
        reply = client.cmd("query-status")
        assert "return" in reply
        dest = tmp_path / "frames" / "a.png"
        client.screendump(dest)
        assert dest.read_bytes() == MIN_PNG
        client.send_key(["n"], hold_ms=80)
        client.input_send_event([{"type": "rel", "data": {"axis": "x", "value": 1}}])
        assert client.hmp("info status") == ""
        kinds = [c["execute"] for c in qmp_server.commands]
        assert "screendump" in kinds
        assert "send-key" in kinds
        assert "input-send-event" in kinds
        assert "human-monitor-command" in kinds
    finally:
        client.close()
        client.close()  # idempotent


def test_events_are_skipped_and_recorded(qmp_server):
    qmp_server.events_before = [{"event": "STOP", "data": {"reason": "test"}}]
    client = QMPClient()
    client.connect(qmp_server.path, timeout_s=5)
    try:
        client.cmd("query-status")
        events = client.events()
        assert any(ev.get("event") == "STOP" for ev in events)
        popped = client.pop_events()
        assert popped
        assert client.events() == []
    finally:
        client.close()


def test_cmd_timeout(qmp_server):
    qmp_server.hang_on = "slow-op"
    client = QMPClient()
    client.connect(qmp_server.path, timeout_s=5)
    try:
        with pytest.raises(TimeoutError, match="timed out"):
            client.cmd("slow-op", timeout_s=0.3)
    finally:
        qmp_server.hang_on = None
        client.close()


def test_qmp_error_does_not_look_like_success(qmp_server):
    qmp_server.error_on["explode"] = {"class": "GenericError", "desc": "boom"}
    client = QMPClient()
    client.connect(qmp_server.path, timeout_s=5)
    try:
        with pytest.raises(QMPError, match="boom"):
            client.cmd("explode")
    finally:
        client.close()


def test_reconnect_after_drop(qmp_server):
    client = QMPClient()
    client.connect(qmp_server.path, timeout_s=5)
    try:
        client.cmd("query-status")
        qmp_server.drop_clients()
        time.sleep(0.2)
        client.reconnect(timeout_s=5)
        assert client.cmd("query-status")["return"] == {}
        assert [c["execute"] for c in qmp_server.commands].count("qmp_capabilities") >= 2
    finally:
        client.close()


def test_connect_fails_on_missing_socket(tmp_path):
    client = QMPClient()
    with pytest.raises(QMPError, match="connect failed"):
        client.connect(tmp_path / "no-such.sock", timeout_s=0.3)
