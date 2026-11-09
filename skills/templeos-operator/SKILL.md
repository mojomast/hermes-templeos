---
name: templeos-operator
description: >-
  Skill id templeos:templeos-operator. Load it with
  skill_view("templeos:templeos-operator"). Drive a local TempleOS-family
  QEMU guest (default TinkerOS 5.20-rc10) with the four templeos_* tools,
  then look or read_text. Open the TempleOS Desktop pane so the user can
  watch and Take control or Hand back. Networking is always off.
version: "0.1.0"
author: mojomast
license: MIT
compatibility: >-
  Python 3.10+, Hermes >= 0.23.0, qemu-system-x86_64 and qemu-img on PATH.
  Linux x86_64 is the primary host. KVM is used only when /dev/kvm can be
  opened; otherwise TCG. No secrets. The plugin does not open a dotenv file.
metadata:
  hermes:
    tags: [templeos, qemu, desktop]
    category: tools
    related_skills: []
---

# TempleOS operator

Drive the local guest with the four tools. Prefer text over screenshots.
Respect the user when they Take control. Networking stays off.

## Tools

| Tool | Ops |
|---|---|
| `templeos_vm` | `start` `stop` `reset` `snapshot` `restore` `status` `doctor` |
| `templeos_screen` | `look` `read_text` `wait_idle` `hash` |
| `templeos_input` | `type` `keys` `click` `move` `holyc` |
| `templeos_files` | `list` `pull` `push` |

Every call returns a JSON string `{ok, error, code, fix, ...}`.

## Loop (do this every time)

1. `templeos_vm op=doctor` if QEMU or the ISO may be missing.
2. `templeos_vm op=start` (default flavor `tinkeros`).
3. `templeos_screen op=wait_idle`, then **`read_text` before `look`**.
4. Act with `templeos_input`. After any consequential `type`, `keys`, `click`, or `holyc`, call **`wait_idle`**, then `read_text` (or one `look` if graphics matter).
5. If you get `agent_paused`, stop injecting. Tell the user the pane is in Take control or the shared hold-off (~2 s), and wait or ask them to click **Hand back**.

### Budgets (per session)

- At most **8** `look` calls. Default 640×480 is ~414 visual tokens; ZealOS 1024×768 is ~1036 — do not switch flavors casually.
- At most **40** input steps (`type` / `keys` / `click` / `move` / `holyc`).
- Prefer `read_text` (serial when COM1 is already open, else 8×8 glyphs). Prune old images from your context.

## HolyC basics (TinkerOS / TempleOS)

- Prompt looks like `T:/Home>`. Statements end with `;`.
- Print: `"hello world\n";`
- List dir: `Dir;` or `Dir("T:/Demo");`
- Change dir: `Cd("T:/Demo");` — `Cd;` goes home.
- Edit: `Ed("File.HC");` (or `Ed;` for a new doc).
- Run a file: `#include "File.HC";` then call its `U0` entry, e.g. `MyFun;`.
- Functions: `U0 Hi(){ "hi\n"; }` then `Hi;`.
- Help: click **Cmd Line** / Command Line Overview, or type `Help;`.

### Serial on TinkerOS (required for `read_text` / files)

`CommInit` is disabled at boot. After a clean prompt:

```
CommInit;
CommInit8n1(1,115200);
```

Then load the helper (source in the repo):

```
#include "Xfer.HC";
XferServe;
```

Push `skills/templeos-operator/guest/Xfer.HC` with `templeos_files op=push` once the serial path works, or type it with `templeos_input op=holyc`. Keep COM1 open on the host for the whole session or guest bytes are lost.

### Keys and menus

- `ret` Enter, `esc` Esc, `f1`–`f10`, arrows as QEMU qcodes.
- First-boot "Install onto hard drive" / "Take Tour" prompts are auto-answered **n** after `op=start` (Esc clears AutoComplete focus first). AutoComplete and the System Keys overlay can still swallow typing — `wait_idle` + `read_text` after surprises.
- Clicks: TinkerOS uses absolute VMMouse (`via=auto`). Stock TempleOS / ZealOS need `MsSet` or relative; absolute QMP events error there.

## Snapshots before risk

Before a risky experiment (raw ports, big `#include`, debugger bait):

1. `templeos_vm op=snapshot` with `name` like `before-xfer` (default `golden` is the clean boot).
2. Experiment.
3. On failure: `templeos_vm op=restore` with that name. If restore left the VM paused, the plugin must `cont` (already contracted).

## Debugger recovery

If you land in the TempleOS / TinkerOS debugger:

1. `templeos_screen op=read_text` or `look` once to confirm.
2. Type recovery, in order:
   - `G2;` — continue (common “go” form).
   - If still stuck: `Exit;` — leave the debugger back toward Adam / the caller.
   - Last resort: `templeos_vm op=restore` to `golden`, or `op=reset`.
3. Do **not** keep typing HolyC that caused the fault in a loop.

Stock TempleOS has no ready `Comm*` on the paths tried in the bake-off; prefer raw `OutU8` only if you know what you are doing, or stay on TinkerOS for serial.

## Files

- `list` / `pull` / `push` use the framed COM1 protocol (`docs/FILES.md`) with the Xfer helper.
- Host `src` / `dest` must stay under the plugin data dir (`TEMPLEOS_HOME`).
- Cap is 256 KiB per file. Never ask to mount the live RedSea qcow2 while QEMU has it open.
- FAT floppy push is **experimental** (bake-off: hot-added FAT12 was not visible as `A:` on TinkerOS). Prefer serial.

## Respect the user

| Pane mode | Your job |
|---|---|
| Watch | Only you inject input; user watches. |
| Shared (default) | Both can type. User key/click → `agent_paused` for ~2 s. |
| Take control (You drive) | All your input ops return `agent_paused` until **Hand back**. |

Never fight the user for the keyboard. Announce what you are about to click when it matters. Open the Desktop pane so they can see the same 640×480 screen.

## Failure codes to honour

| code | What you do |
|---|---|
| `agent_paused` | Wait or ask for Hand back. |
| `serial_not_ready` | Start VM, keep COM1 open, `CommInit` + helper. |
| `qemu_missing` / `iso_missing` / `iso_hash_mismatch` | Run `doctor`; show the fix. |
| `timeout` | Longer `wait_idle`, then one `read_text`. |
| `not_implemented` | Say which slice has not landed yet. |
| Pane blank / stale | User: **Capabilities → Plugins → Rescan**. |

## Safety

Child hypervisor, `-nic none`, unix sockets only, no secrets, no dotenv. Do not ask to enable a NIC. Do not flood `look`. Do not force-push or rewrite guest disks from the host while QEMU is running.
