"""Live-shape AUTH sign-up parsing tests.

Fixtures mirror ``hermes/bbs-server`` ``server/hbbs/bbs1.py`` at 74b4b44 and
the ``hermes/bbs-contracts`` response fixtures 015/016/017.  Tokens are obvious
fixture placeholders and are never real credentials.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from templeos import bbs
from templeos.tools import TOOL_NAMES

CLAIM_TOKEN = "fixture.claim.token.0000000000000001"
ACCESS_TOKEN = "fixture.access.token.0000000000000003"
REFRESH_TOKEN = "fixture.refresh.token.00000000000001"

PENDING_APPLICATION: dict[str, Any] = {
    "application_id": "app_1000000000000001",
    "account": "new_human_2",
    "display_name": "New Human 2",
    "kind": "human",
    "status": "pending_moderation",
    "queue_position": 2,
    "created_at": "2026-11-10T00:00:00Z",
    "trust": "untrusted",
}

APPROVED_APPLICATION: dict[str, Any] = {
    "application_id": "app_3000000000000003",
    "account": "new_human_2",
    "display_name": "New Human 2",
    "kind": "human",
    "status": "approved",
    "queue_position": 0,
    "created_at": "2026-11-10T00:00:00Z",
    "trust": "untrusted",
}

PENDING_SIGNUP_DATA: dict[str, Any] = {
    "application": dict(PENDING_APPLICATION),
    "claim_token": CLAIM_TOKEN,
    "claim_expires_at": "2026-11-11T00:00:00Z",
}

PENDING_STATUS_DATA: dict[str, Any] = {
    "application": dict(PENDING_APPLICATION),
    "claim_expires_at": "2026-11-11T00:00:00Z",
}

APPROVED_STATUS_DATA: dict[str, Any] = {
    "grant": "signup",
    "application": dict(APPROVED_APPLICATION),
    "session": {
        "session_id": "ses_3000000000000003",
        "issued_at": "2026-11-10T00:16:00Z",
        "expires_at": "2026-11-10T00:17:00Z",
    },
    "account": {
        "account": "new_human_2",
        "display_name": "New Human 2",
        "kind": "human",
        "role": "human",
        "trust": "untrusted",
    },
    "moderation": {"state": "approved", "can_read": True, "can_post": True},
    "limits": {"role": "human"},
    "writable_boards": ["general", "holyc", "lore"],
    "access_token": ACCESS_TOKEN,
    "refresh_token": REFRESH_TOKEN,
}


def _wire(data: dict[str, Any]) -> dict[str, Any]:
    """Round-trip through the exact HBBS/1 success envelope."""

    frame = bbs.encode_response("AUTH", data=data, frame_id="r-015")
    parsed = bbs.read_frame(_socketpair_with(frame))
    assert parsed.type == "RSP"
    return parsed.json()["data"]


def _socketpair_with(frame: bytes):
    import socket

    left, right = socket.socketpair()
    left.sendall(frame)
    left.close()
    return right


# --- pending signup --------------------------------------------------------


def test_pending_signup_parses_nested_application_and_top_level_claim() -> None:
    data = _wire(PENDING_SIGNUP_DATA)
    result = bbs.parse_signup_data(data)
    assert result.application_id == "app_1000000000000001"
    assert result.account == "new_human_2"
    assert result.display_name == "New Human 2"
    assert result.kind == "human"
    assert result.status == "pending_moderation"
    assert result.queue_position == 2
    assert result.trust == "untrusted"
    assert result.claim_token == CLAIM_TOKEN
    assert result.claim_expires_at == "2026-11-11T00:00:00Z"
    assert result.pending is True
    assert result.approved is False
    assert result.access_token is None and result.refresh_token is None


def test_pending_signup_requires_top_level_claim_token() -> None:
    data = dict(PENDING_SIGNUP_DATA)
    data.pop("claim_token")
    with pytest.raises(bbs.BbsProtocolError) as caught:
        bbs.parse_signup_data(data)
    assert caught.value.code == "bbs_protocol_error"


def test_pending_signup_rejects_claim_nested_inside_application() -> None:
    data = {
        "application": dict(PENDING_APPLICATION, claim_token=CLAIM_TOKEN),
        "claim_expires_at": "2026-11-11T00:00:00Z",
    }
    with pytest.raises(bbs.BbsProtocolError):
        bbs.parse_signup_data(data)


def test_old_top_level_application_id_shape_is_rejected() -> None:
    legacy = {
        "application_id": "app_1000000000000001",
        "status": "pending_moderation",
        "claim_token": CLAIM_TOKEN,
    }
    with pytest.raises(bbs.BbsProtocolError):
        bbs.parse_signup_data(legacy)


# --- pending signup_status -------------------------------------------------


def test_pending_signup_status_tolerates_missing_claim_token() -> None:
    data = _wire(PENDING_STATUS_DATA)
    assert "claim_token" not in data
    result = bbs.parse_signup_status(data)
    assert result.application_id == "app_1000000000000001"
    assert result.status == "pending_moderation"
    assert result.claim_token is None
    assert result.claim_expires_at == "2026-11-11T00:00:00Z"


def test_pending_signup_status_accepts_echoed_claim_token() -> None:
    result = bbs.parse_signup_status(PENDING_SIGNUP_DATA)
    assert result.claim_token == CLAIM_TOKEN


# --- approved signup_status ------------------------------------------------


def test_approved_signup_status_parses_grant_and_tokens() -> None:
    data = _wire(APPROVED_STATUS_DATA)
    result = bbs.parse_signup_status(data)
    assert result.grant == "signup"
    assert result.status == "approved"
    assert result.approved is True
    assert result.pending is False
    assert result.application_id == "app_3000000000000003"
    assert result.queue_position == 0
    assert result.access_token == ACCESS_TOKEN
    assert result.refresh_token == REFRESH_TOKEN
    assert result.claim_token is None


def test_approved_signup_also_parses_grant_and_tokens() -> None:
    result = bbs.parse_signup_data(APPROVED_STATUS_DATA)
    assert result.approved is True
    assert result.grant == "signup"
    assert result.access_token == ACCESS_TOKEN
    assert result.refresh_token == REFRESH_TOKEN


def test_approved_without_grant_is_rejected() -> None:
    data = dict(APPROVED_STATUS_DATA)
    data.pop("grant")
    with pytest.raises(bbs.BbsProtocolError):
        bbs.parse_signup_status(data)


@pytest.mark.parametrize("missing", ["access_token", "refresh_token"])
def test_approved_without_session_tokens_is_rejected(missing: str) -> None:
    data = dict(APPROVED_STATUS_DATA)
    data.pop(missing)
    with pytest.raises(bbs.BbsProtocolError):
        bbs.parse_signup_status(data)


def test_approved_application_id_must_match_live_pattern() -> None:
    for bad in ("app_1", "app_ABCDEFGHIJKLMNOP", "1000000000000001", ""):
        data = dict(APPROVED_STATUS_DATA)
        data["application"] = dict(APPROVED_APPLICATION, application_id=bad)
        with pytest.raises(bbs.BbsProtocolError):
            bbs.parse_signup_status(data)


def test_repr_never_contains_tokens() -> None:
    result = bbs.parse_signup_status(APPROVED_STATUS_DATA)
    text = repr(result)
    assert ACCESS_TOKEN not in text
    assert REFRESH_TOKEN not in text
    pending = bbs.parse_signup_data(PENDING_SIGNUP_DATA)
    assert CLAIM_TOKEN not in repr(pending)


# --- structured sign-up errors --------------------------------------------


def _server_error(payload: dict[str, Any]) -> bbs.BbsServerError:
    frame = bbs.encode_response("AUTH", error=payload, frame_id="r-020")
    parsed = bbs.read_frame(_socketpair_with(frame))
    body = parsed.json()
    assert body["ok"] is False
    error = body["error"]
    return bbs.BbsServerError(error["code"], error["message"], field=error.get("field"))


def test_account_pending_maps_from_server_error() -> None:
    error = _server_error(
        {
            "code": "account_pending",
            "message": "account is awaiting moderation",
            "field": "args.account",
        }
    )
    assert error.code == "account_pending"
    assert error.field == "args.account"
    assert bbs.signup_error_code(error) == "account_pending"


def test_account_exists_maps_from_server_error() -> None:
    error = _server_error(
        {
            "code": "account_exists",
            "message": "account already exists",
            "field": "args.account",
        }
    )
    assert error.code == "account_exists"
    assert bbs.signup_error_code(error) == "account_exists"


def test_unrelated_errors_are_not_signup_outcomes() -> None:
    error = bbs.BbsServerError("rate_limited", "rate limit exceeded")
    assert bbs.signup_error_code(error) is None
    assert bbs.signup_error_code(bbs.BbsError("plain")) is None


# --- immediate 0600 persistence -------------------------------------------


def test_persist_signup_claim_writes_owner_only_file(tmp_path: Path) -> None:
    target = tmp_path / "private" / "creds"
    path = bbs.persist_signup_claim(
        target,
        application_id="app_1000000000000001",
        account="toh-dialtest2",
        status="pending_moderation",
        claim_token=CLAIM_TOKEN,
        claim_expires_at="2026-11-11T00:00:00Z",
    )
    assert path == target.resolve()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    text = path.read_text()
    assert "APPLICATION_ID=app_1000000000000001" in text
    assert "ACCOUNT=toh-dialtest2" in text
    assert f"CLAIM_TOKEN={CLAIM_TOKEN}" in text
    assert oct(stat.S_IMODE(path.stat().st_mode)) == "0o600"


def test_persist_approved_tokens_are_file_only(tmp_path: Path) -> None:
    path = bbs.persist_signup_claim(
        tmp_path / "creds",
        application_id="app_3000000000000003",
        account="toh-dialtest2",
        status="approved",
        claim_token=CLAIM_TOKEN,
        access_token=ACCESS_TOKEN,
        refresh_token=REFRESH_TOKEN,
    )
    text = path.read_text()
    assert f"ACCESS_TOKEN={ACCESS_TOKEN}" in text
    assert f"REFRESH_TOKEN={REFRESH_TOKEN}" in text
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_persist_refuses_repository_and_shots_paths(tmp_path: Path) -> None:
    repo_root = Path(bbs.__file__).resolve().parents[1]
    for bad in (repo_root / "creds", repo_root / "shots" / "bbs-dial" / "creds", tmp_path / "shots" / "creds"):
        with pytest.raises(bbs.BbsValidationError):
            bbs.persist_signup_claim(
                bad,
                application_id="app_1000000000000001",
                account="toh-dialtest2",
                claim_token=CLAIM_TOKEN,
            )


def test_persist_rejects_invalid_application_id(tmp_path: Path) -> None:
    with pytest.raises(bbs.BbsValidationError):
        bbs.persist_signup_claim(
            tmp_path / "creds",
            application_id="app_1",
            account="toh-dialtest2",
            claim_token=CLAIM_TOKEN,
        )


def test_persist_does_not_leave_token_in_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise OSError("denied")

    monkeypatch.setattr(os, "replace", refuse)
    with pytest.raises(bbs.BbsConfigError) as caught:
        bbs.persist_signup_claim(
            tmp_path / "creds",
            application_id="app_1000000000000001",
            account="toh-dialtest2",
            claim_token=CLAIM_TOKEN,
        )
    assert CLAIM_TOKEN not in str(caught.value)
    assert CLAIM_TOKEN not in json.dumps(caught.value.as_envelope())


# --- client callers use the nested shape ----------------------------------


def test_client_signup_application_parses_nested_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    client = bbs.BbsClient()
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_request(command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((command, dict(args or {})))
        return dict(PENDING_SIGNUP_DATA)

    monkeypatch.setattr(client, "request", fake_request)
    result = client.signup_application("toh-dialtest2", "Temple dial test 2", "human")
    assert result.application_id == "app_1000000000000001"
    assert result.claim_token == CLAIM_TOKEN
    assert calls == [
        (
            "AUTH",
            {
                "action": "signup",
                "account": "toh-dialtest2",
                "display_name": "Temple dial test 2",
                "kind": "human",
            },
        )
    ]


def test_client_signup_and_persist_writes_before_returning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = bbs.BbsClient()

    def fake_request(command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict(PENDING_SIGNUP_DATA)

    monkeypatch.setattr(client, "request", fake_request)
    target = tmp_path / "creds"
    result = client.signup_and_persist(
        "toh-dialtest2",
        "Temple dial test 2",
        "human",
        path=target,
    )
    assert result.application_id == "app_1000000000000001"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    text = target.read_text()
    assert "APPLICATION_ID=app_1000000000000001" in text
    assert "ACCOUNT=new_human_2" in text
    assert f"CLAIM_TOKEN={CLAIM_TOKEN}" in text


def test_client_signup_application_status_parses_nested_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    client = bbs.BbsClient()

    def fake_request(command: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        return dict(PENDING_STATUS_DATA)

    monkeypatch.setattr(client, "request", fake_request)
    result = client.signup_application_status("app_1000000000000001", CLAIM_TOKEN)
    assert result.status == "pending_moderation"
    assert result.claim_token is None


def test_four_tools_remain() -> None:
    assert TOOL_NAMES == ("templeos_vm", "templeos_screen", "templeos_input", "templeos_files")
    assert len(TOOL_NAMES) == 4
