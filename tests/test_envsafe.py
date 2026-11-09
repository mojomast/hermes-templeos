from __future__ import annotations

from pathlib import Path

from templeos.envsafe import CHILD_ENV_ALLOWLIST, child_env


def test_child_env_is_an_allowlist(monkeypatch, tos_home):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("ORBIT_TOKEN", "orbit-leak")
    monkeypatch.setenv("NODE_OPTIONS", "--require leak")
    monkeypatch.setenv("PYTHONHOME", "/should-not-pass")
    monkeypatch.setenv("PYTHONPATH", "/also-not")
    monkeypatch.setenv("LD_PRELOAD", "evil.so")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = child_env()
    assert "OPENAI_API_KEY" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "ORBIT_TOKEN" not in env
    assert "NODE_OPTIONS" not in env
    assert "PYTHONHOME" not in env
    assert "PYTHONPATH" not in env
    assert "LD_PRELOAD" not in env
    assert env["LC_ALL"] == "C.UTF-8"
    assert env["LANG"] == "en_US.UTF-8"
    assert env["SSL_CERT_FILE"] == "/etc/ssl/cert.pem"
    assert env["PATH"]
    assert env["TEMPLEOS_HOME"] == str(tos_home)
    assert set(env) <= set(CHILD_ENV_ALLOWLIST)


def test_child_env_rejects_undeclared_extra():
    try:
        child_env({"OPENAI_API_KEY": "nope"})
    except ValueError as exc:
        assert "undeclared" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_dotenv_is_not_read(monkeypatch, tmp_path, tos_home):
    envfile = tmp_path / ".env"
    envfile.write_text("OPENAI_API_KEY=from-dotenv\nTEMPLEOS_HOME=/tmp/hacked\n")
    monkeypatch.setenv("TEMPLEOS_ENV_FILE", str(envfile))
    # TEMPLEOS_HOME is already set by the fixture; dotenv must not override it.
    from templeos.paths import home

    assert home() == tos_home.resolve()
    src = Path(__file__).resolve().parents[1]
    blob = "\n".join(
        p.read_text()
        for p in src.rglob("*.py")
        if "tests" not in p.parts and p.suffix == ".py"
    )
    assert "load_dotenv" not in blob
    assert "from dotenv" not in blob
    assert "import dotenv" not in blob
