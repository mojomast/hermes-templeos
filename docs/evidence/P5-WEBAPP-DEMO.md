# P5 — Hermes web app + TempleOS plugin demo

## Verdict

**BLOCKED on model access.** Hermes, the plugin, the gateway web app, headless
Chromium (dark), and the TempleOS pane are installed and running, and the
plugin's own VM tools work under TCG. The only model credential present in the
worker environment has no usable quota, so the web-app chat could not complete a
turn and the agent never called `templeos_*`.

No key was copied from the host, the owner's home, or any orchestrator path. No
sign-in link, cookie, or auth header is included in this report or the patch.

## Environment

| Item | Value |
| --- | --- |
| Hermes Agent | v0.23.0 (2026.9.24), local install commit `2bd378ed1b8d` |
| Plugin source | `mojomast/hermes-templeos`, branch `feat/p1-agent-tools` |
| Plugin SHA | `8eaae18ffcecffd7fbef7c7e59e3580b2b1c1b50` |
| Install mode | immutable SHA via `hermes plugins install ... --ref <sha> --yes-deps --no-enable` |
| Enable | `hermes plugins enable templeos --no-allow-tool-override` |
| Toolsets | `templeos` enabled for `cli` and `api_server` (`hermes tools list --platform ...`) |
| ISO | TinkerOS 5.20-rc10, SHA-256 verified `feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4` |
| QEMU | 8.2.2, no `/dev/kvm` in the sandbox, so `tcg` |
| QEMU flags observed | `-machine pc,kernel-irqchip=off -accel tcg -display none -nic none` |
| Gateway | web app on `127.0.0.1:9120` (not the 9119 dashboard) |
| Browser | headless Chromium 155, dark colour scheme |
| Pane mode | Shared (not Take control), guest running on TCG |

## What actually ran in the chat

Prompt sent in a new chat:

```text
type a HolyC one-liner that prints 'Hello from Hermes' and 6*7
```

The gateway returned a model quota error before any assistant turn:

```text
rate limited — resets in ~23h 5m, retrying in 600s (attempt 1/3)
FreeUsageLimitError: Free usage limit reached.
```

There was no `tool_search` call, no `tool_call`, and no `templeos_*` call. A
redacted trace is therefore just the user prompt plus the rate-limit status;
there are no auth headers, cookies, links, or model output to redact.

## Why the chat could not run

The worker environment exposes exactly one model credential. It was used only
inside the sandbox and never printed or copied. Diagnosis, without values:

- OpenAI rejects it (HTTP 401).
- OpenRouter rejects it (HTTP 401).
- It authenticates to the OpenCode Zen-compatible endpoint, but paid models
  return HTTP 402 (insufficient account funds).
- Free models return HTTP 429 `FreeUsageLimitError` from this sandbox, with the
  provider stating the free allowance is exhausted.
- No other provider credential is present in the worker environment.

Per the task rules, no credential was sourced from another location and no key
was invented. The blocker is model quota, not the plugin or the VM.

## Supplementary plugin check (not agent-driven)

To separate a plugin failure from the model blocker, the installed plugin's own
tool implementations were invoked directly under the same TCG guest. This is
**not** evidence that the agent used the tools; it only shows that the tools
themselves work:

- `templeos_vm op=start` → `ok`, `attached: true`, `accel: tcg`
- `templeos_input` type path (the same QEMU input route used by `op=holyc`,
  with a slower per-key delay): `"Hello from Hermes\n";` then `6*7;`
- `templeos_screen op=read_text` → both `Hello from Hermes` and `42` present
- `templeos_screen op=look` → 640×480 PNG captured

The default-speed `holyc` typing path garbled characters under this TCG guest
(`6*7;` became `67;`, and Shift-quoted text was reordered), so the supplementary
check used the same input route with a slower inter-key delay. This is worth
rechecking on the agent path; it does not affect the blocker above.

The desktop half was enabled as an opt-in plugin and the TempleOS pane was
visible beside the transcript in Shared mode, showing the running TCG guest.

## Evidence files

- `shots/p5-webapp-demo/webapp-chat-dark.png` — full-window dark capture: new
  chat with the exact prompt and the quota/rate-limit status, TempleOS pane
  visible beside the transcript in Shared mode. This is a blocker capture, not
  an agent success turn.
- `shots/p5-webapp-demo/vm-result.png` — 640×480 `templeos_screen op=look`
  capture. The guest shows `"Hello from Hermes\n";` → `Hello from Hermes` and
  `6*7;` → `42` (`ans=0x0000002A=42`).

## Acceptance status

| Check | Result |
| --- | --- |
| Hermes + plugin from `feat/p1-agent-tools` at `8eaae18` installed | pass |
| Gateway web app on 9120 + headless Chromium dark mode | pass |
| TempleOS pane beside transcript, Shared/Watch | pass |
| Agent used `templeos_*` tools | **fail** — model quota blocked the turn |
| Chat screenshot shows `Hello from Hermes` and `42` | **fail** — chat shows the rate-limit status instead |
| Plugin VM tools work under TCG | pass (direct tool check, not agent-driven) |
| No real Hermes keys taken from the box | pass |
| Only assigned files changed | pass |
| No secrets in the patch | pass |

## Open issues

1. **No usable model quota.** The worker environment needs a model credential
   with available quota for this sandbox. Until then the chat cannot produce an
   agent tool trace.
2. Re-run the exact prompt once model access exists, confirm the trace contains
   `templeos_vm`, `templeos_screen`, and `templeos_input` (possibly via
   `tool_search`/`tool_call`), and replace the blocker chat capture with the
   successful chat + pane capture.
3. The pane's live frame can go black while the guest idles; a keypress wakes
   it. This is cosmetic and not the cause of the blocker.
4. Default-speed `templeos_input op=holyc` typing garbled characters under this
   TCG guest. Slower per-key typing on the same input route worked. Recheck this
   on the first real agent turn.
