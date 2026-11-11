# Bee brief: TempleOS plugin web app demo

Live verification that a Hermes **web app** chat (gateway `127.0.0.1:9120`, not the dashboard on 9119) uses the four `templeos_*` tools to type a HolyC one-liner, and that the guest shows `Hello from Hermes` and `42`.

This is a **cua / bee** job. Do not run the live QEMU demo on the shared Hermes box unless the owner explicitly lifts the "no QEMU on the box" order. Prefer the owner's machine, or a host they name.

Repo: `mojomast/hermes-templeos`, branch `feat/improvements` (PR #2, stacked on `feat/integration` / PR #1). Check out the tip of that branch (the commit that adds the Tool Search system prompt section, holyc typing default, Shift-chord `input-send-event`, and QEMU reattach). Do not merge, tag, force-push, or deploy to a test host.

## What you are proving

The earlier failure: the web app agent ignored `templeos_vm` / `templeos_screen` / `templeos_input` / `templeos_files` and wrote its own VNC/socket script.

Root cause: Hermes Tool Search defers plugin tools by default, so the model never saw the `templeos_*` schemas. It used terminal tools instead. Two related bugs made a tool-using path fail even if the agent found the tools: `holyc via=auto` silently dropped bytes when the host COM1 socket was open but the guest had not run `CommInit`, and TinkerOS under TCG dropped Shift so `"` became `'`. After a gateway restart, `start` also returned `vm_already_running` without rebinding QMP, so tools looked dead while QEMU was still up.

The fix (already in this branch): a short `register_system_prompt_section`, skill v0.1.2, tighter tool descriptions, `via=auto` types until `Runtime.guest_serial_ready`, Shift chords go down / hold / up, and `start` (and other running-VM ops) reattach to a live QEMU.

Success looks like: the agent calls `templeos_*` (via `tool_search`/`tool_call` if deferred), not a VNC client; the pane or a `templeos_screen` capture shows `Hello from Hermes` and `42`.

## Preconditions

- Plugin checkout at `feat/improvements`, enabled with `hermes plugins enable templeos --no-allow-tool-override`. If the `~/.hermes/plugins/templeos` symlink was moved, re-enable after pointing it back.
- `platform_toolsets.cli` includes `templeos`. `api_server` gets plugin toolsets by default unless a saved list omitted them. Confirm with `hermes tools list --platform cli` and `--platform api_server`.
- Desktop bundle is already current (`node scripts/build_desktop.mjs --check`). If you rebuild, copy `desktop/plugin.js` to `~/.hermes/desktop-plugins/templeos/plugin.js`.
- One TinkerOS guest only. If a `qemu-system-x86_64 -name templeos-tinkeros` is already running, **reuse it**. After a gateway restart, `templeos_vm op=start` should reattach (`attached: true`) instead of failing. Do not start a second QEMU.
- Gateway is the web app one on `127.0.0.1:9120`. Restart it only if the new plugin code is not loaded; SIGTERM the gateway process and let the supervisor relaunch it. Do not print env, tokens, or private URLs.
- Python unit tests and the JS `--check` tests already passed on this branch; do not rerun a full heavy suite on the shared box.

## Mint the web app link (secret)

```bash
hermes webapp --no-open --skip-build
```

Store the one-use sign-in link **only** in `/workspace/templeos-webapp-link.txt` with mode `0600`. The link is a secret: never print it, never commit it, never paste it into a ticket, log, or chat. It expires in about 60 seconds once minted, so mint immediately before the browser step.

## What to type in the chat

New chat, **dark mode**, TempleOS pane visible beside the transcript:

> type a HolyC one-liner that prints 'Hello from Hermes' and 6*7

The agent should roughly: `tool_search(["templeos"])` or `skill_view("templeos:templeos-operator")` if tools are deferred; `templeos_vm op=status` (start if needed, which reattaches a live guest); `templeos_screen op=wait_idle` then `read_text` until a `T:/Home>` prompt; Esc if AutoComplete stole focus; `templeos_input op=holyc` with a source such as `"Hello from Hermes\n"; 6*7;`; then `wait_idle` and `read_text`. Fail the demo if it writes a VNC client, dials `~/.hermes/plugin-data/templeos/sockets/*`, or runs `screendump`/`qemu` by hand.

## API verification (do this even without a screenshot)

If the gateway API is reachable, drive or observe the same prompt and confirm the tool trace contains `templeos_vm`, `templeos_screen`, and `templeos_input` (possibly wrapped in `tool_search`/`tool_call`). Then capture the guest:

- Call `templeos_screen op=look` (or the plugin `/frame` / look path) and save the PNG at `/workspace/templeos-demo/vm-result.png`.
- Call `templeos_screen op=read_text` and record whether the text includes `Hello from Hermes` and `42`.

Do not dump authorization headers, cookies, or the sign-in link when reporting.

## Screenshot steps (desktop helper)

If you have no browser, hand this to a desktop helper. Do not include the sign-in link in the handoff; tell them the path to the 0600 file instead.

1. Open the link from `/workspace/templeos-webapp-link.txt` immediately after minting (60s one-use). This is the Hermes **web app**, not the dashboard at port 9119.
2. Switch the UI to **dark mode**.
3. Start a new chat. Open the TempleOS pane so the guest screen is visible next to the transcript (Shared or Watch is fine; do not leave it in Take control).
4. Send: `type a HolyC one-liner that prints 'Hello from Hermes' and 6*7`.
5. Wait until the agent finishes. Confirm the tool list shows `templeos_*` (or tool_search then those tools), not a custom VNC script.
6. Confirm the pane shows `Hello from Hermes` and `42`.
7. Screenshot the full window: chat transcript plus TempleOS pane. Save under `/workspace/templeos-demo/` (e.g. `webapp-chat-dark.png`) in addition to `vm-result.png`.

## Report back

- Branch SHA tested, Hermes version (`hermes --version`), and host (box vs owner machine).
- Whether the agent used `templeos_*` tools, including any `tool_search` calls, and a short redacted tool trace.
- Whether `read_text` / the screenshot show `Hello from Hermes` and `42`.
- Paths of `vm-result.png` and the chat screenshot.
- Anything that still failed (tools still deferred and ignored, Shift quotes, serial drop, attach after restart).

Do not merge, tag, force-push, or deploy.
