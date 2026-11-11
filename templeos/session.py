"""Host-side community operations: session summary, BBS digest, codeshare.

Everything here is a host helper behind the existing four tools. Fetched HolyC
is staged under the plugin data dir, pushed only into the guest Src/ folder,
and can run only through the guest input path. Nothing is executed on the host.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from templeos import bbs, nudge
from templeos.paths import home

DEFAULT_JOURNAL_LINES = 5
MAX_JOURNAL_LINES = 10
MAX_LINE_CHARS = 200
MAX_CODE_BYTES = 32 * 1024
GUEST_RUN_TIMEOUT_S = 15.0
DEFAULT_HANDLE = "hermes"
ENV_HANDLE = "TEMPLEOS_HANDLE"
MAX_DIGEST_ITEMS = 10
MAX_SUBJECT_CHARS = 60

_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_POST_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_FILENAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
_COUNT_KEYS = ("replies", "unread", "unread_replies", "mail", "unread_mail", "threads", "posts")
_SOURCE_KEYS = ("source", "code", "holyc", "body", "text", "content")


class OpsError(Exception):
    def __init__(self, message: str, code: str, fix: str | None = None, **fields: Any) -> None:
        super().__init__(message)
        self.code = code
        self.fix = fix
        self.fields = fields
        self.envelope = {"error": message, "code": code, "fix": fix, **fields}


def _handle(handle: str | None = None) -> str:
    value = (handle or os.environ.get(ENV_HANDLE) or DEFAULT_HANDLE).strip()
    if not _HANDLE_RE.match(value) or value in (".", ".."):
        raise OpsError(
            "handle must be 1-32 letters, digits, dots, dashes, or underscores.",
            "invalid_args",
            "Pass a simple guest home handle, e.g. handle=hermes.",
        )
    return value


def guest_home(handle: str | None = None) -> str:
    return f"C:/Home/{_handle(handle)}"


def _clean_line(value: Any, limit: int = MAX_LINE_CHARS) -> str:
    text = str(value or "").replace("\x00", " ")
    text = " ".join(text.split())
    return text[:limit]


def _read_guest_text(guest_path: str, pull: Callable[..., Mapping[str, Any]] | None = None) -> str:
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix=".session-") as tmp:
        dest = Path(tmp) / "file.txt"
        fn = pull
        if fn is None:
            from templeos.files import pull as fn
        result = fn(guest_path, dest)
        if not isinstance(result, Mapping) or result.get("ok") is False:
            raise OpsError(
                f"Could not read {guest_path} from the guest.",
                "session_unavailable",
                "Start the guest, load the Xfer helper, and create the Home journal/projects files.",
            )
        try:
            return dest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raise OpsError(
                f"Could not read {guest_path} after transfer.",
                "session_unavailable",
                "Retry once the guest serial file helper is responsive.",
            ) from None


def _journal_lines(text: str, limit: int) -> list[str]:
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_clean_line(line) for line in raw if _clean_line(line)]
    return lines[-limit:]


def _projects_summary(text: str) -> tuple[str | None, str | None]:
    current = None
    next_step = None
    fallback: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = _clean_line(raw)
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            key, sep, value = line.partition("=")
        if sep:
            normalized = re.sub(r"[^a-z]+", "", key.lower())
            if normalized in ("current", "project", "currentproject"):
                current = _clean_line(value)
                continue
            if normalized in ("next", "nextstep", "todo"):
                next_step = _clean_line(value)
                continue
        fallback.append(line)
    if current is None and fallback:
        current = fallback[0]
    if next_step is None and len(fallback) > 1:
        next_step = fallback[1]
    return current, next_step


def session_start(
    *,
    limit: int = DEFAULT_JOURNAL_LINES,
    handle: str | None = None,
    pull: Callable[..., Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    try:
        lines_wanted = int(limit)
    except (TypeError, ValueError):
        raise OpsError("limit must be an integer.", "invalid_args", "Use limit 1-10.")
    lines_wanted = max(1, min(MAX_JOURNAL_LINES, lines_wanted))
    home_guest = guest_home(handle)
    journal_path = f"{home_guest}/JOURNAL.TXT"
    projects_path = f"{home_guest}/PROJECTS.TXT"
    journal_text = _read_guest_text(journal_path, pull)
    projects_text = _read_guest_text(projects_path, pull)
    journal = _journal_lines(journal_text, lines_wanted)
    project, next_step = _projects_summary(projects_text)
    if not journal and project is None and next_step is None:
        raise OpsError(
            "The session files are present but empty.",
            "session_unavailable",
            "Write a journal line and a project/next step in the guest Home folder.",
        )
    if project or next_step:
        nudge.record_pending(project=project, next_step=next_step)
    return {
        "ok": True,
        "handle": _handle(handle),
        "journal": journal,
        "journal_count": len(journal),
        "project": project,
        "next_step": next_step,
    }


def _count(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _safe_id(value: Any) -> str | None:
    text = str(value or "")
    return text if _POST_RE.match(text) else None


def _safe_subject(value: Any) -> str:
    text = _clean_line(value, MAX_SUBJECT_CHARS)
    return text


def _normalize_digest(data: Mapping[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    source = data
    for key in ("counts", "digest"):
        nested = source.get(key) if isinstance(source, Mapping) else None
        if isinstance(nested, Mapping):
            source = nested
            break
    for key in _COUNT_KEYS:
        if key in source:
            counts[key] = _count(source.get(key))
    ids: list[str] = []
    for key in ("ids", "post_ids", "thread_ids"):
        values = data.get(key)
        if isinstance(values, list):
            for value in values:
                safe = _safe_id(value)
                if safe and safe not in ids:
                    ids.append(safe)
    subjects: list[str] = []
    items = data.get("subjects")
    if items is None:
        items = data.get("items") if isinstance(data.get("items"), list) else data.get("recent")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                title = item.get("subject") or item.get("title") or item.get("name")
            else:
                title = item
            text = _safe_subject(title)
            if text:
                subjects.append(text)
    replies = counts.get("replies", 0) + counts.get("unread_replies", 0)
    mail = counts.get("mail", 0) + counts.get("unread_mail", 0)
    unread = counts.get("unread", 0)
    pending = max(replies + mail, unread)
    return {
        "counts": counts,
        "ids": ids[:MAX_DIGEST_ITEMS],
        "subjects": subjects[:MAX_DIGEST_ITEMS],
        "pending": pending,
        "truncated": len(ids) > MAX_DIGEST_ITEMS or len(subjects) > MAX_DIGEST_ITEMS,
    }


def _bbs_failure(exc: BaseException) -> OpsError:
    code = getattr(exc, "code", None) or "bbs_unavailable"
    if code in ("bbs_disabled", "bbs_config_error"):
        return OpsError(
            "The BBS destination is not configured.",
            "bbs_not_configured",
            "Ask the human to set the bbs endpoint in host env/config; there is no default host.",
        )
    return OpsError(
        "The BBS request failed.",
        str(code),
        "Check host connectivity and the configured bbs endpoint, then retry.",
    )


def _open_client(factory: Callable[..., Any] | None) -> Any:
    if factory is not None:
        return factory()
    return bbs.open_destination()


def bbs_digest(
    *,
    limit: int = 10,
    client_factory: Callable[..., Any] | None = None,
    config_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if client_factory is None:
        try:
            config = (config_factory or bbs.load_config)()
        except bbs.BbsError as exc:
            raise _bbs_failure(exc) from None
        except Exception:
            raise OpsError(
                "The BBS destination is not configured.",
                "bbs_not_configured",
                "Ask the human to set the bbs endpoint in host env/config; there is no default host.",
            ) from None
        if not getattr(config, "enabled", False):
            raise OpsError(
                "The BBS destination is not configured.",
                "bbs_not_configured",
                "Ask the human to set the bbs endpoint in host env/config; there is no default host.",
            )
    client = None
    try:
        client = _open_client(client_factory)
        if hasattr(client, "connect"):
            client.connect()
        data = client.digest(limit=max(1, min(20, int(limit))))
    except OpsError:
        raise
    except bbs.BbsError as exc:
        raise _bbs_failure(exc) from None
    except Exception:
        raise OpsError(
            "The BBS digest request failed.",
            "bbs_unavailable",
            "Check the configured bbs endpoint and retry.",
        ) from None
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    if not isinstance(data, Mapping):
        raise OpsError("The BBS digest reply was malformed.", "bbs_protocol_error", "Check the server version.")
    body = _normalize_digest(data)
    nudge.record_pending(bbs_replies=body["pending"])
    return {"ok": True, **body}


def _extract_source(data: Mapping[str, Any]) -> str | None:
    for key in _SOURCE_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("post", "source", "download", "item"):
        nested = data.get(key)
        if isinstance(nested, Mapping):
            found = _extract_source(nested)
            if found:
                return found
    return None


def _source_name(data: Mapping[str, Any], post_id: str) -> str:
    name = data.get("filename") or data.get("name") or data.get("path")
    base = Path(str(name)).name if name else f"post-{post_id}"
    base = _FILENAME_RE.sub("-", base).strip("-.") or f"post-{post_id}"
    if len(base) > 48:
        base = base[:48]
    if base.lower().endswith(".hc"):
        base = base[:-3] + ".HC"
    else:
        base += ".HC"
    return base


def _run_in_guest(source: str) -> dict[str, Any]:
    from templeos.input import holyc
    from templeos.screen import wait_idle

    result = holyc(source)
    if not isinstance(result, Mapping) or result.get("ok") is False:
        return dict(result) if isinstance(result, Mapping) else {"ok": False, "code": "vm_not_running"}
    idle = wait_idle(timeout_s=GUEST_RUN_TIMEOUT_S)
    return {"ok": True, "guest_run": dict(idle) if isinstance(idle, Mapping) else None}


def codeshare_fetch(
    post_id: str,
    *,
    run: bool = False,
    handle: str | None = None,
    client_factory: Callable[..., Any] | None = None,
    push: Callable[..., Mapping[str, Any]] | None = None,
    run_source: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    post = str(post_id or "").strip()
    if not _POST_RE.match(post):
        raise OpsError(
            "post_id must be a simple board id.",
            "invalid_args",
            "Use the id from a bbs_digest result.",
        )
    client = None
    try:
        client = _open_client(client_factory)
        if hasattr(client, "connect"):
            client.connect()
        data = client.download(post, board="holyc")
    except OpsError:
        raise
    except bbs.BbsError as exc:
        raise _bbs_failure(exc) from None
    except Exception:
        raise OpsError(
            "The codeshare download failed.",
            "bbs_unavailable",
            "Check the configured bbs endpoint and retry.",
        ) from None
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
    if not isinstance(data, Mapping):
        raise OpsError("The codeshare reply was malformed.", "bbs_protocol_error", "Check the server version.")
    source = _extract_source(data)
    if source is None:
        raise OpsError(
            "The codeshare reply did not include HolyC source.",
            "invalid_source",
            "Fetch a post that contains source text.",
        )
    raw = source.encode("utf-8")
    if len(raw) > MAX_CODE_BYTES:
        raise OpsError(
            f"Fetched source exceeds {MAX_CODE_BYTES} bytes.",
            "source_too_large",
            "Choose a smaller post; fetched HolyC is capped at 32 KiB.",
        )
    name = _source_name(data, post)
    guest_path = f"{guest_home(handle)}/Src/{name}"
    root = home()
    root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=root, prefix=".codeshare-")) / name
    try:
        stage.write_bytes(raw)
        try:
            stage.chmod(0o600)
        except OSError:
            pass
        pusher = push
        if pusher is None:
            from templeos.files import push as pusher
        pushed = pusher(stage, guest_path)
        if not isinstance(pushed, Mapping) or pushed.get("ok") is False:
            raise OpsError(
                "Could not write the fetched source into the guest Src folder.",
                str((pushed or {}).get("code") or "codeshare_push_failed") if isinstance(pushed, Mapping) else "codeshare_push_failed",
                "Start the guest and load the Xfer helper, then retry the fetch.",
            )
    finally:
        try:
            stage.unlink()
        except OSError:
            pass
        try:
            stage.parent.rmdir()
        except OSError:
            pass
    result: dict[str, Any] = {
        "ok": True,
        "post_id": post,
        "guest_path": guest_path,
        "bytes": len(raw),
        "ran": False,
    }
    if run:
        runner = run_source or _run_in_guest
        ran = runner(source)
        if not isinstance(ran, Mapping) or ran.get("ok") is False:
            raise OpsError(
                "The source was saved but the in-guest run failed.",
                str((ran or {}).get("code") or "guest_run_failed") if isinstance(ran, Mapping) else "guest_run_failed",
                "Check that the guest is running at a HolyC prompt, then run it from the guest.",
                guest_path=guest_path,
            )
        result["ran"] = True
        result["guest_run"] = dict(ran)
    return result
