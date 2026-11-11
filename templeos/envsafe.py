"""Child-process environment allowlist.

QEMU and qemu-img always receive an explicit minimal env. Default inheritance
(omitting env=) is unsafe. No dotenv, no secrets (this plugin declares none),
no prefix-wide copies, no NODE_OPTIONS or PYTHONHOME.
"""

from __future__ import annotations

import os
from typing import Mapping

# Exact names only. Do not add prefix-wide rules (no TEMPLEOS_*, no NODE_*, no LC_*).
CHILD_ENV_ALLOWLIST: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LANGUAGE",
        "TZ",
        "TMPDIR",
        "TMP",
        "TEMP",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "TEMPLEOS_HOME",
    }
)

_DEFAULT_PATH = "/usr/bin:/bin"
_DEFAULT_LANG = "C.UTF-8"
_BLOCKED_ALWAYS = frozenset(
    {
        "NODE_OPTIONS",
        "PYTHONHOME",
        "PYTHONPATH",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "DYLD_LIBRARY_PATH",
    }
)


def child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build the environment passed to QEMU and other children.

    ``extra`` may only set names already on the allowlist. Values are taken
    from the current process for allowlisted names that are set and non-empty.
    """
    env: dict[str, str] = {}
    for key in CHILD_ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value:
            env[key] = value
    if extra:
        for key, value in extra.items():
            if key not in CHILD_ENV_ALLOWLIST:
                raise ValueError(f"refusing to pass undeclared env name {key!r} to a child process")
            if key in _BLOCKED_ALWAYS:
                raise ValueError(f"refusing to pass blocked env name {key!r} to a child process")
            if value:
                env[key] = value
    for blocked in _BLOCKED_ALWAYS:
        env.pop(blocked, None)
    env.setdefault("PATH", _DEFAULT_PATH)
    env.setdefault("LANG", _DEFAULT_LANG)
    env.setdefault("LC_ALL", env.get("LC_ALL") or _DEFAULT_LANG)
    return env
