"""Offline human-then-agent join and authenticated digest tests."""

from __future__ import annotations

import json
import socket
import ssl
import stat
import threading
from pathlib import Path
from typing import Any, Callable

import pytest

from templeos import bbs, session

from tests.test_bbs_transport import _TEST_CERT_B64, _TEST_KEY_B64, _decode


class JoinServer:
    """A multi-connection loopback HBBS/1 server with signup/refresh/digest."""

    def __init__(self, cert: Path, key: Path, *, fail_first_human: bool = False, rate_limit_first: bool = False) -> None:
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(str(cert), str(key))
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.listener.settimeout(0.2)
        self.port = int(self.listener.getsockname()[1])
        self.frames: list[bbs.Frame] = []
        self.accounts: set[str] = set()
        self.tokens: dict[str, str] = {}
        self.refresh_serials: list[str] = []
        self.fail_first_human = fail_first_human
        self.rate_limit_first = rate_limit_first
        self.failed_once = False
        self.rate_limited_once = False
        self.errors: list[BaseException] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._serial = 0

    @property
    def endpoint(self) -> str:
        return f"tls://127.0.0.1:{self.port}"

    def __enter__(self) -> "JoinServer":
        self._thread = threading.Thread(target=self._serve, name="bbs-join-server", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self._stop.set()
        try:
            self.listener.close()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                raw, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self.errors.append(exc)
                return
            try:
                with self.context.wrap_socket(raw, server_side=True) as tls:
                    self._session(tls)
            except (bbs.BbsError, OSError, ssl.SSLError) as exc:
                self.errors.append(exc)

    def _session(self, tls: ssl.SSLSocket) -> None:
        authed = False
        while not self._stop.is_set():
            try:
                frame = bbs.read_frame(tls)
            except bbs.BbsError:
                return
            self.frames.append(frame)
            body = frame.json()
            command = frame.command
            args = body.get("args") or {}
            if not authed and command != "AUTH":
                tls.sendall(
                    bbs.encode_response(
                        command,
                        error={"code": "auth_required", "message": "AUTH must be first"},
                        frame_id=frame.frame_id,
                    )
                )
                return
            if command == "AUTH":
                action = args.get("action")
                if action == "signup":
                    account = str(args.get("account"))
                    if self.rate_limit_first and not self.rate_limited_once:
                        self.rate_limited_once = True
                        tls.sendall(
                            bbs.encode_response(
                                "AUTH",
                                error={"code": "rate_limited", "message": "slow down", "retry_after": 1},
                                frame_id=frame.frame_id,
                            )
                        )
                        continue
                    if self.fail_first_human and not self.failed_once and args.get("kind") == "human":
                        self.failed_once = True
                        tls.sendall(
                            bbs.encode_response(
                                "AUTH",
                                error={"code": "account_exists", "message": "account already exists"},
                                frame_id=frame.frame_id,
                            )
                        )
                        continue
                    if account in self.accounts:
                        tls.sendall(
                            bbs.encode_response(
                                "AUTH",
                                error={"code": "account_exists", "message": "account already exists"},
                                frame_id=frame.frame_id,
                            )
                        )
                        continue
                    if args.get("kind") == "agent" and args.get("owner_account") not in self.accounts:
                        tls.sendall(
                            bbs.encode_response(
                                "AUTH",
                                error={"code": "owner_not_eligible", "message": "owner is not active"},
                                frame_id=frame.frame_id,
                            )
                        )
                        continue
                    self.accounts.add(account)
                    authed = True
                    access, refresh = self._mint(account)
                    tls.sendall(bbs.encode_response("AUTH", data=self._approved(account, args, access, refresh), frame_id=frame.frame_id))
                    continue
                if action == "refresh":
                    token = str(args.get("refresh_token"))
                    account = self.tokens.get(token)
                    if not account:
                        tls.sendall(
                            bbs.encode_response(
                                "AUTH",
                                error={"code": "invalid_token", "message": "refresh token is invalid"},
                                frame_id=frame.frame_id,
                            )
                        )
                        continue
                    authed = True
                    access, refresh = self._mint(account)
                    tls.sendall(
                        bbs.encode_response(
                            "AUTH",
                            data={
                                "grant": "refresh",
                                "account": {"account": account, "kind": "agent", "role": "agent"},
                                "access_token": access,
                                "refresh_token": refresh,
                            },
                            frame_id=frame.frame_id,
                        )
                    )
                    continue
                if action == "login":
                    authed = True
                    tls.sendall(bbs.encode_response("AUTH", data={"grant": "login", "account": {"account": "unknown", "role": "agent"}}, frame_id=frame.frame_id))
                    continue
                tls.sendall(bbs.encode_response("AUTH", error={"code": "invalid_args", "message": "bad auth"}, frame_id=frame.frame_id))
                continue
            if command == "LIST" and args.get("action") == "digest":
                tls.sendall(
                    bbs.encode_response(
                        "LIST",
                        data={
                            "digest": {
                                "generated_at": "2026-11-12T00:00:00Z",
                                "since": None,
                                "cursor": None,
                                "mail": {
                                    "unread": 1,
                                    "latest": [
                                        {
                                            "message_id": "msg_1",
                                            "subject": "mail hello",
                                            "body": "raw mail body must not leak",
                                        }
                                    ],
                                },
                                "mentions": {
                                    "pending": 1,
                                    "latest": [
                                        {
                                            "post_id": "post_2",
                                            "subject": "mention hello",
                                            "body": "raw mention body must not leak",
                                        }
                                    ],
                                },
                                "replies": {
                                    "count": 1,
                                    "latest": [
                                        {
                                            "post_id": "post_1",
                                            "subject": "hello",
                                            "body": "raw reply body must not leak",
                                        }
                                    ],
                                },
                                "followed_boards": [{"board_id": "holyc", "title": "HolyC"}],
                                "trust": "untrusted",
                                "access_token": "must-not-leak-token",
                            }
                        },
                        frame_id=frame.frame_id,
                    )
                )
                continue
            if command == "DOWNLOAD":
                tls.sendall(
                    bbs.encode_response(
                        "DOWNLOAD",
                        data={"source": "Dir;\n", "filename": "demo.hc"},
                        frame_id=frame.frame_id,
                    )
                )
                continue
            tls.sendall(
                bbs.encode_response(
                    command,
                    error={"code": "unknown_command", "message": "not in fixture"},
                    frame_id=frame.frame_id,
                )
            )

    def _mint(self, account: str) -> tuple[str, str]:
        self._serial += 1
        access = f"fixture.access.{self._serial:016d}"
        refresh = f"fixture.refresh.{self._serial:016d}"
        self.tokens[refresh] = account
        self.refresh_serials.append(refresh)
        return access, refresh

    def _approved(self, account: str, args: dict[str, Any], access: str, refresh: str) -> dict[str, Any]:
        self._serial += 1
        kind = str(args.get("kind"))
        return {
            "grant": "signup",
            "application": {
                "application_id": f"app_{self._serial:016d}",
                "account": account,
                "display_name": str(args.get("display_name")),
                "kind": kind,
                "status": "approved",
                "queue_position": 0,
                "created_at": "2026-11-12T00:00:00Z",
                "trust": "untrusted",
            },
            "session": {"session_id": f"ses_{self._serial:016d}"},
            "account": {"account": account, "kind": kind, "role": kind},
            "access_token": access,
            "refresh_token": refresh,
        }


@pytest.fixture
def certs(tmp_path: Path) -> tuple[Path, Path]:
    cert = tmp_path / "join-cert.pem"
    key = tmp_path / "join-key.pem"
    cert.write_bytes(_decode(_TEST_CERT_B64))
    key.write_bytes(_decode(_TEST_KEY_B64))
    return cert, key


def _env(monkeypatch: pytest.MonkeyPatch, server: JoinServer, cert: Path) -> None:
    monkeypatch.setenv(bbs.ENV_ENABLED, "1")
    monkeypatch.setenv(bbs.ENV_ENDPOINT, server.endpoint)
    monkeypatch.setenv(bbs.ENV_CA_FILE, str(cert))
    monkeypatch.delenv(bbs.ENV_SERVER_NAME, raising=False)


def _commands(server: JoinServer) -> list[str]:
    return [frame.command for frame in server.frames]


def _auth_actions(server: JoinServer) -> list[str]:
    actions = []
    for frame in server.frames:
        if frame.command != "AUTH":
            continue
        args = frame.json().get("args") or {}
        actions.append(str(args.get("action")))
    return actions


def _json_cred(tos_home: Path, kind: str, account: str) -> Path:
    prefix = "human-" if kind == "human" else "agent-"
    return tos_home / "bbs" / f"{prefix}{account}.json"


def test_join_signs_up_human_then_agent_and_keeps_tokens_out_of_output(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        body = session.bbs_join(handle="toh-alice", display_name="Alice")
        assert body["ok"] is True
        assert body["joined"] is True
        assert body["human_account"].startswith("toh-alice")
        assert body["agent_account"].endswith("-agent")
        assert body["status"] == "joined"
        text = json.dumps(body)
        for marker in ("fixture.access", "fixture.refresh", "CLAIM_TOKEN", "ACCESS_TOKEN"):
            assert marker not in text
        human = _json_cred(tos_home, "human", body["human_account"])
        agent = _json_cred(tos_home, "agent", body["agent_account"])
        for path in (human, agent):
            assert path.is_file()
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
            payload = json.loads(path.read_text())
            assert "refresh_token" in payload
            assert "access_token" in payload
        assert server.accounts == {body["human_account"], body["agent_account"]}
        actions = [a for a in _auth_actions(server) if a == "signup"]
        assert actions == ["signup", "signup"]
        agent_frame = next(
            frame for frame in server.frames if frame.command == "AUTH" and (frame.json().get("args") or {}).get("kind") == "agent"
        )
        assert (agent_frame.json().get("args") or {}).get("owner_account") == body["human_account"]


def test_join_is_idempotent_via_refresh_and_does_not_sign_up_again(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        first = session.bbs_join(handle="toh-bob")
        signups = _auth_actions(server).count("signup")
        agent = _json_cred(tos_home, "agent", first["agent_account"])
        before = agent.read_text()
        second = session.bbs_join(handle="toh-bob")
        assert second["joined"] is True
        assert second["agent_account"] == first["agent_account"]
        assert _auth_actions(server).count("signup") == signups
        assert "refresh" in _auth_actions(server)
        after = agent.read_text()
        assert before != after
        assert "refresh_token" in json.loads(after)


def test_join_increments_account_when_account_exists(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1], fail_first_human=True) as server:
        _env(monkeypatch, server, certs[0])
        body = session.bbs_join(handle="toh-carol")
        assert body["joined"] is True
        assert body["human_account"] != "toh-carol"
        assert body["human_account"].endswith("2")


def test_digest_authenticates_with_stored_agent_creds(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        joined = session.bbs_join(handle="toh-dave")
        assert joined["joined"] is True
        start = len(server.frames)
        body = session.bbs_digest()
        assert body["ok"] is True
        assert body["counts"] == {"mail": 1, "mentions": 1, "replies": 1}
        assert body["pending"] == 3
        assert {"post_1", "post_2", "msg_1", "holyc"} <= set(body["ids"])
        assert "hello" in body["subjects"]
        later = server.frames[start:]
        assert [frame.command for frame in later[:2]] == ["AUTH", "LIST"]
        assert (later[0].json().get("args") or {}).get("action") == "refresh"
        digest_args = later[1].json().get("args") or {}
        assert digest_args.get("action") == "digest"
        assert "board" not in digest_args
        assert "limit" not in digest_args
        text = json.dumps(body)
        assert "must-not-leak-token" not in text
        assert "raw mail body must not leak" not in text
        assert "raw mention body must not leak" not in text
        assert "raw reply body must not leak" not in text
        assert "fixture." not in text


def test_status_reports_agent_account_and_never_tokens(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        before = session.bbs_status()
        assert before["enabled"] is True
        assert before["configured"] is True
        assert before["joined"] is False
        joined = session.bbs_join(handle="toh-erin")
        status = session.bbs_status()
        assert status["joined"] is True
        assert status["account"] == joined["agent_account"]
        text = json.dumps(status)
        assert "fixture." not in text
        assert "TOKEN" not in text


def test_join_adopts_existing_json_layout_without_signing_up(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adopt human-<account>.json / agent-<account>.json (AUTH JSON), do not re-signup.

    Test accounts are throwaway names only; never reuse live community accounts.
    """
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        human_account = "toh-zoe"
        agent_account = "toh-zoe-agent"
        human_access, human_refresh = server._mint(human_account)
        agent_access, agent_refresh = server._mint(agent_account)
        server.accounts.update({human_account, agent_account})
        bbs_dir = tos_home / "bbs"
        bbs_dir.mkdir(mode=0o700)
        human_payload = {
            "grant": "signup",
            "account": {"account": human_account, "kind": "human", "role": "human"},
            "access_token": human_access,
            "refresh_token": human_refresh,
            "status": "approved",
        }
        agent_payload = {
            "grant": "signup",
            "account": {"account": agent_account, "kind": "agent", "role": "agent"},
            "access_token": agent_access,
            "refresh_token": agent_refresh,
            "status": "approved",
        }
        human = _json_cred(tos_home, "human", human_account)
        agent = _json_cred(tos_home, "agent", agent_account)
        human.write_text(json.dumps(human_payload))
        agent.write_text(json.dumps(agent_payload))
        human.chmod(0o600)
        agent.chmod(0o600)
        body = session.bbs_join(handle="toh-zoe")
        assert body["ok"] is True
        assert body["joined"] is True
        assert body["agent_account"] == agent_account
        assert body["human_account"] == human_account
        assert "signup" not in _auth_actions(server)
        assert "refresh" in _auth_actions(server)
        assert "fixture." not in json.dumps(body)
        status = session.bbs_status()
        assert status["joined"] is True
        assert status["account"] == agent_account
        assert "fixture." not in json.dumps(status)


def test_join_still_reads_legacy_key_value_creds(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    with JoinServer(certs[0], certs[1]) as server:
        _env(monkeypatch, server, certs[0])
        human_account = "toh-wendy"
        agent_account = "toh-wendy-agent"
        _ha, human_refresh = server._mint(human_account)
        _aa, agent_refresh = server._mint(agent_account)
        server.accounts.update({human_account, agent_account})
        bbs_dir = tos_home / "bbs"
        bbs_dir.mkdir(mode=0o700)
        (bbs_dir / "human.creds").write_text(
            f"ACCOUNT={human_account}\nREFRESH_TOKEN={human_refresh}\n"
        )
        (bbs_dir / "agent.creds").write_text(
            f"ACCOUNT={agent_account}\nREFRESH_TOKEN={agent_refresh}\n"
        )
        (bbs_dir / "human.creds").chmod(0o600)
        (bbs_dir / "agent.creds").chmod(0o600)
        body = session.bbs_join(handle="toh-wendy")
        assert body["joined"] is True
        assert body["agent_account"] == agent_account
        assert "signup" not in _auth_actions(server)


def test_join_retries_once_after_rate_limited(
    tos_home: Path, certs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[int] = []
    monkeypatch.setattr(session.time, "sleep", lambda seconds: sleeps.append(int(seconds)))
    with JoinServer(certs[0], certs[1], rate_limit_first=True) as server:
        _env(monkeypatch, server, certs[0])
        body = session.bbs_join(handle="toh-frank")
        assert body["joined"] is True
        assert body["human_account"].startswith("toh-frank")
        assert sleeps == [1]
        assert _auth_actions(server).count("signup") >= 2

