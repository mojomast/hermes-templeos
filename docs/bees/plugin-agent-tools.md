# Bee brief: finish the TempleOS agent-tools fix

Handoff for a bee to complete remaining verification (and any follow-up code) so the Hermes **web app** agent uses the four `templeos_*` tools instead of writing a VNC client.

Repo: `mojomast/hermes-templeos`. Branch: `feat/improvements` (PR #2, stacked on `feat/integration` / PR #1). Base SHA before this work: `4bff5af`. The code fix is already committed as `111340ff9d9d4e1b685de189cb56367acc6d4d5e` (`fix: steer agents to templeos_* tools and reattach a live QEMU`). Do not merge, tag, force-push, or deploy to a test host.

The live chat + VM screenshot is a separate brief: `docs/bees/plugin-webapp-demo.md`. Use that for the dark-mode web app demo. Do **not** start QEMU on the shared Hermes box unless the owner lifts the "no QEMU on the box" order.

## Root cause (so far)

When Kyle asked the Hermes web app (`hermes webapp`, gateway `127.0.0.1:9120`) to type a HolyC one-liner that prints `Hello from Hermes` and `6*7`, the agent did not call `templeos_vm` / `templeos_screen` / `templeos_input` / `templeos_files`. It wrote its own VNC/socket script instead.

This was not mainly a missing `platform_toolsets` or enable-flag bug:

- The plugin is enabled (`plugins.enabled` includes `templeos`).
- `platform_toolsets.cli` includes `templeos`. `api_server` also shows the templeos plugin toolset enabled (`hermes tools list --platform api_server`).
- The four tools are registered under toolset `templeos`.

The primary cause is **Hermes Tool Search**. With `tools.tool_search.enabled: auto` (the default), plugin tools are deferrable: they are dropped from the model-facing tool list and replaced by `tool_search` / `tool_describe` / `tool_call`. The agent never saw the `templeos_*` schemas, so it used terminal tools and invented a VNC workaround. Updating tool descriptions alone is not enough, because deferred schemas are not in the first prompt.

Related bugs that would still break a tool-using path:

1. `holyc via=auto` treated a host-open COM1 socket as "serial ready". The guest had not run `CommInit` / `CommInit8n1`, so the source was written to COM1 and silently dropped.
2. TinkerOS under TCG often dropped Shift when QMP `send-key` fired a chord in one packet, so `"` became `'`.
3. After a gateway restart, QEMU can stay up (pidfile + sockets) while the in-process runtime is gone. `start` returned `vm_already_running` and did not rebind QMP/COM1, so later tools failed with `vm_not_running`.

## What is already in `111340f`

| Area | Change |
|---|---|
| `__init__.py` | Registers system prompt section `templeos-operator` (`TEMPLEOS_SYSTEM_PROMPT_SECTION`) so the agent is told to `tool_search(["templeos"])` or `skill_view("templeos:templeos-operator")` and never to write a VNC client. Still installs pane agent-log hooks at `register()`. |
| `skills/templeos-operator/SKILL.md` | v0.1.2: Tool Search steps, forbidden workarounds, HolyC one-liner loop with `op=holyc`. |
| `templeos/tools.py` | Longer tool descriptions steering `tool_search` and forbidding VNC; handlers come from `HANDLERS` after log hooks wrap them. |
| `templeos/input.py` | `via=auto` types unless `Runtime.guest_serial_ready`; modifier chords use `input-send-event` down, a short hold, then up; `type_text` skips the hold when `delay_s==0` (unit-test seam). |
| `templeos/screen.py` | `Runtime.guest_serial_ready` flag (default False). |
| `templeos/vm.py` | `_attach_existing()`: `start` and `_require_running` reattach QMP/COM1 to a live QEMU after a gateway restart (`attached: true`). Same-process second `start` is idempotent and returns status. |
| Tests | `tests/test_plugin.py`, `tests/test_input.py`, `tests/test_vm.py`, `tests/fakes.py`. |
| Docs | `CHANGELOG.md`, `README.md`, `docs/bees/plugin-webapp-demo.md`. |

Light checks already run on that commit (niced, no live QEMU, `TEMPLEOS_SMOKE` unset):

- `pytest -q tests/test_input.py tests/test_vm.py tests/test_plugin.py tests/test_tools.py tests/test_contracts.py` → **34 passed, 1 skipped**.
- `PATH=~/.local/node22/bin:$PATH node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs` → **16 passed**.
- `node scripts/build_desktop.mjs --check` → `desktop/plugin.js is up to date` (no JS change; no copy to `~/.hermes/desktop-plugins/templeos/plugin.js` was needed).
- `python3 evals/measure_schemas.py` → **892** o200k tokens (**+67** vs the 0.1.0 baseline of 825). Still four tools, under the ~2,000 cap.

## Remaining steps

1. Confirm `feat/improvements` is pushed (no force-push) at or after `111340f`, plus this brief if you commit it.
2. On a host that is allowed to run the guest (not the shared box unless the owner says so), load the new plugin code: point `~/.hermes/plugins/templeos` at this checkout, `hermes plugins enable templeos --no-allow-tool-override`, and restart only the web app gateway (`127.0.0.1:9120`) if it is still running the old `register()`. SIGTERM the gateway process and let the supervisor relaunch it. Do not print env, tokens, or the one-use sign-in link.
3. Follow `docs/bees/plugin-webapp-demo.md` for the dark-mode web app chat demo and `/workspace/templeos-demo/vm-result.png`. The user prompt is: `type a HolyC one-liner that prints 'Hello from Hermes' and 6*7`. Expect `Hello from Hermes` and `42`. Fail if the agent writes a VNC client or dials plugin-data sockets.
4. If the agent still skips `templeos_*` after the system prompt section is loaded, strengthen the steer (do not turn Tool Search off globally). Options: tighten the prompt section, confirm the gateway actually loaded this SHA, or check that `api_server`/`cli` still has the templeos toolset. Re-run only the affected unit tests, niced (`nice -n 19`).
5. Optional follow-up, not required for the demo: set `Runtime.guest_serial_ready = True` after a successful guest `Comm*` / files protocol exchange so `holyc via=auto` can use serial when it is truly live. Until then, auto types at the prompt, which is the correct default.
6. Do not merge, tag, release, or deploy to a test host without an explicit yes from Kyle.

## Acceptance

- `feat/improvements` on GitHub includes the prompt section, holyc typing default, Shift-chord down/hold/up, and QEMU reattach.
- A web app chat (gateway 9120, dark mode, TempleOS pane visible) for the HolyC one-liner uses `templeos_*` tools (via `tool_search`/`tool_call` if deferred), not a VNC/socket workaround.
- The guest screen or `templeos_screen op=read_text` shows `Hello from Hermes` and `42`. Evidence: a redacted tool trace plus `/workspace/templeos-demo/vm-result.png` and a chat+pane screenshot.
- Light unit tests still pass if you change code; no extra QEMU on the shared box; no force-push; schema stays under ~2,000 o200k.

## Report back

SHA tested, Hermes version, host, whether the agent called `templeos_*`, whether the guest showed the two results, paths of artifacts, and any remaining gap. Do not print the web app sign-in link or other secrets.
