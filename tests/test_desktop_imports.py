"""The Hermes web app only exports hooks from "react", not "react/jsx-runtime"."""
import re
from pathlib import Path

PLUGIN_JS = Path(__file__).resolve().parents[1] / "desktop" / "plugin.js"


def test_hooks_come_from_react_not_jsx_runtime():
    text = PLUGIN_JS.read_text(encoding="utf-8")
    bad = re.findall(r'import \{ (use\w+) as \w+ \} from "react/jsx-runtime"', text)
    assert bad == [], f"hooks imported from react/jsx-runtime: {bad}"
