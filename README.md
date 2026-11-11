<div align="center">

# TempleOS for Hermes

**A local TempleOS-family guest in QEMU. The Hermes agent and you share one live screen.**

Default flavor is [Temple of Hermes](https://github.com/mojomast/temple-of-hermes) 0.1.2.
[TinkerOS](https://github.com/tinkeros/TinkerOS) 5.20-rc10, stock [TempleOS](https://templeos.org/) 5.03, and [ZealOS](https://github.com/Zeal-Operating-System/ZealOS) are optional.
Networking is always off. QEMU and ISOs are not bundled.

[![License: MIT](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Version 0.1.1](https://img.shields.io/badge/version-0.1.1-8b5cf6)](plugin.yaml)
[![Hermes >=0.23.0](https://img.shields.io/badge/Hermes-%3E%3D0.23.0-111827)](plugin.yaml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-pytest%20%2B%20node-0ea5e9)](#development)

<p>
<img src="docs/images/pane-1920x1240.png" alt="World-class TempleOS Desktop pane at 1920x1240: guest screen and activity log on the left, HD Terry on the right" width="960">
</p>
<p>
<img src="docs/images/pane-typing.png" alt="HD Terry typing beside the live TempleOS guest screen" width="680">
<img src="docs/images/pane-narrow.png" alt="Narrow pane layout with the guest screen and HD Terry stacked in columns" width="300">
</p>

<sub>
In memory of <strong>Terry A. Davis</strong> (1969–2018), author of TempleOS.
TempleOS is public domain. This plugin is an unofficial Hermes integration; see
[Credits](#credits).
</sub>

[Quickstart](#quickstart) · [Tools](#tools) · [Pane](#desktop-pane) · [Flavors](#flavors) · [Temple of Hermes](#temple-of-hermes-guest) · [Architecture](#architecture) · [Security](#security-and-disclosures) · [Troubleshooting](#troubleshooting) · [Development](#development)

</div>

---

> **Credit and respect.** TempleOS is Terry A. Davis's public-domain operating system —
> a 64-bit hobby OS with a HolyC compiler, 640×480 16-color graphics, and no network stack
> in the original design. Read the [official downloads](https://templeos.org/Downloads/),
> [Credits](https://templeos.info/Wb/Doc/Credits.DD.HTML), and be decent when you demo it.
> [TinkerOS](https://github.com/tinkeros/TinkerOS) and [ZealOS](https://github.com/Zeal-Operating-System/ZealOS)
> are community forks. This plugin defaults to [Temple of Hermes](https://github.com/mojomast/temple-of-hermes) 0.1.2,
> a public-domain TinkerOS 5.20-rc10 fork. TinkerOS stays selectable; the bake-off proved absolute
> mouse clicks and Adam `Comm*` serial there.

## What it is

1. **Doctor.** Finds `qemu-system-x86_64`, reports whether `/dev/kvm` can be **opened** (not just whether the node exists), and can fetch the pinned ISO from its official URL with SHA-256 verification.
2. **Start.** Boots Temple of Hermes 0.1.2 (or another flavor) in a child QEMU with `-nic none`, QMP / VNC / COM1 on unix sockets under the plugin data dir, and a writable qcow2 so `savevm` works even on a live CD.
3. **See.** `read_text` prefers COM1 when it is already open; otherwise 8×8 glyphs. `look` returns a PNG (not JPEG) at 640×480 by default (~414 visual tokens).
4. **Act.** Type, send QEMU keys, click / move (VMMouse absolute on TinkerOS), or inject HolyC. After each consequential act: `wait_idle`, then `read_text` or one `look`.
5. **Share.** The Desktop pane shows the same screen. **Take control** / **Hand back** pause the agent with `agent_paused`. Shared mode holds off agent input for ~2 s after you type or click.
6. **Files.** Framed COM1 protocol with a small HolyC helper ([docs/FILES.md](docs/FILES.md)). Host paths stay under the plugin data dir. Never mounts the live RedSea qcow2 while QEMU has it open.
7. **Companion.** HD Terry is on by default in the pane: six animation states, 69 sourced quotes, and **Hide Terry** / **Quotes** controls. The four tools and their schemas are unchanged.

**Skill id:** `templeos:templeos-operator` — load with `skill_view("templeos:templeos-operator")`.

## Quickstart

Plugin id is **`templeos`** (`plugin.yaml` `name`). Hermes requirement is **`>=0.23.0`**.

### System QEMU

```bash
# Debian / Ubuntu
sudo apt install qemu-system-x86 qemu-utils

# Fedora
sudo dnf install qemu-system-x86 qemu-img

# Arch
sudo pacman -S qemu-system-x86 qemu-img

# macOS (TCG only; untested as a primary host)
brew install qemu
```

KVM on Linux needs permission to **open** `/dev/kvm` (group `kvm` is typical). If open fails, the plugin falls back to TCG.

### Install the plugin

```bash
hermes plugins install mojomast/hermes-templeos --enable
hermes plugins doctor templeos
```

Doctor does not install packages. It tells you the apt/brew command, fetches the default Temple of Hermes 0.1.2 ISO from the official GitHub release when missing, verifies the pinned SHA-256, and creates the data-dir layout. There is **no catalog pin yet** — do not treat [docs/catalog/templeos.yaml](docs/catalog/templeos.yaml) as a submitted entry (SHA is a zero placeholder on purpose).

After an update, if the Desktop pane is missing or stale: **Capabilities → Plugins → Rescan**.

### Environment

| Name | Role |
| --- | --- |
| `TEMPLEOS_HOME` | Plugin data root (ISOs, disks, sockets, frames, exchange). Must not be a filesystem root. Default: Hermes plugin data dir / XDG fallback. |
| `TEMPLEOS_SMOKE` | `1` enables optional live-QEMU smoke tests (needs a pinned ISO already on disk). |
| `TOH_BBS_ENABLED` | Opt-in switch for the Temple of Hermes BBS bridge. The bridge is **off by default**; no socket opens until this is enabled. |
| `TOH_BBS_ENDPOINT` | TLS endpoint used only when the BBS bridge is enabled. There is no compiled-in default endpoint. |
| `TEMPLEOS_CHAT_BRIDGE` | Opt-in Temple of Hermes chat bridge (off by default). |
| `TEMPLEOS_CHAT_BRIDGE_ENDPOINT` | HTTP(S) agent reply URL used only when the chat bridge is enabled. Plain HTTP is loopback-only. |
| `TEMPLEOS_CHAT_BRIDGE_TOKEN` | Optional bearer token. Declared in `requires_env` and read only through Hermes `get_secret`. Never from `os.environ`. |

No dotenv. The only declared secret is the optional chat-bridge token. The BBS bridge accepts only the allow-list destination name `bbs`; transport details come from host configuration, never from guest text.

## Tools

Hermes **Tool Search** defers plugin tools by default, so their schemas are not in the first tool list. The plugin registers a short system prompt section that tells the agent to `tool_search(["templeos"])` or `skill_view("templeos:templeos-operator")` and never to write a VNC client or dial plugin-data sockets. Desktop/web app and `api_server` sessions should have the `templeos` toolset enabled (`platform_toolsets.cli` already lists it; `api_server` gets plugin toolsets by default unless a saved list omitted them). Prefer `templeos_input op=holyc` for HolyC one-liners. If QEMU is still running after a gateway restart, `templeos_vm op=start` reattaches instead of failing with `vm_already_running`.

Four tools, registered from `templeos/tools.py` under toolset `templeos`. Every handler returns a JSON string `{ok, error, code, fix, ...}`.

| Tool | Ops | Role |
| --- | --- | --- |
| `templeos_vm` | `start` `stop` `reset` `snapshot` `restore` `status` `doctor` `modem` | Child QEMU lifecycle. `snapshot` ejects non-qcow2 writables first; `restore` issues `cont` if `loadvm` left the VM paused; `modem` is a serial profile, not a NIC. Sockets are existence flags only, never tokens. |
| `templeos_screen` | `look` `read_text` `wait_idle` `hash` `lore` | PNG look, serial/glyph text, cropped idle wait, frame hash, and operator lore. Full-frame hashes never stabilize (clock / FPS). |
| `templeos_input` | `type` `keys` `click` `move` `holyc` | Keyboard, pointer, and HolyC. Returns `agent_paused` when you drive or during the shared hold-off. |
| `templeos_files` | `list` `pull` `push` `rpc` | Guest paths like `T:/Home/`; host `src`/`dest` confined under `TEMPLEOS_HOME`. Serial Xfer protocol; `rpc` probes the guest daemon; FAT push is experimental. |

### Bundled skill

`skills/templeos-operator/SKILL.md` registers as `templeos-operator`. The id inside the file is **`templeos:templeos-operator`**. It teaches `read_text` before `look`, `wait_idle` after input, HolyC idioms, debugger recovery (`G2;` / `Exit;`), snapshot etiquette, hand-back respect, and per-session look/step budgets.

## Desktop pane

The Hermes Desktop pane (`desktop/plugin.js`, needs Hermes `>=0.23.0`) talks only through `ctx.rest` to `/api/plugins/templeos/`. It does not dial `127.0.0.1`, does not read parent tokens, and does not load remote scripts.

| Mode | Behaviour |
| --- | --- |
| Watch | You see the VM; only the agent injects input. |
| Shared (default) | Both can type. Your key/click pauses the agent ~2 s. |
| Take control | Agent tools return `agent_paused` until **Hand back**. |

Frames are PNG, integer-scaled from 640×480 (ZealOS may present 1024×768). The pane polls at most ~4–5 fps (slower when idle, hidden, or the host is slow); `/frame` is served from a background cache so capture never blocks the Hermes gateway. Blob URLs are revoked when the next frame arrives.

On a fresh ISO boot (no `golden` snapshot), `templeos_vm op=start` auto-dismisses the first-boot **Install onto hard drive** and **Take Tour** prompts in the background (Esc clears AutoComplete focus, then `n` + Enter). Restore a snapshot to skip them.

<p>
<img src="docs/images/tinkeros-prompt.png" alt="TinkerOS HolyC prompt" width="400">
<img src="docs/images/tinkeros-click.png" alt="Absolute click opened Command Line Overview" width="400">
</p>

### HD Terry companion

Terry is the pane's **default video renderer**: six silent 720×1080 transparent VP9 loops at 20 fps — **idle**, **typing**, **speaking**, **wave**, **walk**, and **smoking** as an occasional idle variant. The quote picker reads **69 sourced quotes** from [desktop/terry-quotes.json](desktop/terry-quotes.json); every entry carries a `source_title` and `source_url`, and quote text appears only in the pane bubble.

If VP9 alpha cannot play, the pane falls back to the **v4 canvas rig**. **Hide Terry** hides or restores the sprite, and the **Quotes on / Quotes muted** toggle controls bubbles without hiding Terry. The costume dropdown appears only on the v4 fallback. You can also disable the companion with `companion: off` or `TEMPLEOS_COMPANION=off`; the pane hide toggle only conceals it.

Attribution: **"An original fan tribute with no official TempleOS affiliation."** Pack notes and clip hashes: [desktop/assets/companion/terry/v5/README.md](desktop/assets/companion/terry/v5/README.md).

Source screenshots also live under [`desktop/screenshots/`](desktop/screenshots/).

## Flavors

Default flavor id is `templeoh` (alias `temple-of-hermes`). TinkerOS, stock TempleOS, and ZealOS stay selectable. ISO pins (SHA-256 and size) live in `templeos/flavors.py`. Official HTTPS URLs only — not Internet Archive. The Desktop pane has a Guest OS picker that shows the selected image version and SHA state; the choice is saved through the `/settings` `ctx.rest` route (also `templeos_vm op=flavor`). If the ISO is not cached yet, doctor fetches the official pin and verifies SHA-256. A running guest applies the new image on the next boot.

| | **Temple of Hermes 0.1.2** (default) | **TinkerOS 5.20-rc10** | **TempleOS 5.03** | **ZealOS** |
| --- | --- | --- | --- | --- |
| Id | `templeoh` | `tinkeros` | `templeos` | `zealos` |
| Resolution / tokens | 640×480 / ~414 | 640×480 / ~414 | 640×480 / ~414 | 1024×768 / ~1036 |
| Mouse | VMMouse (absolute) | VMMouse (absolute) | no abs handler | relative |
| Serial | `Comm*` → COM1 | `Comm*` → COM1 proven | Raw `OutU8` only | Raw `OutU8`; `Comm*` fragile |
| Disk bus | IDE | IDE | IDE | AHCI required |
| Official ISO | GitHub release v0.1.2 | GitHub Releases 5.20-rc10 | templeos.org | ZealOS releases |

Bake-off timings on 9 Nov 2026 (TCG; `/dev/kvm` existed but was not openable on that host; networking off): TinkerOS and TempleOS 5.03 reached a desktop in ~14 s; ZealOS in ~16 s with AHCI. Screendump averages were ~12 ms / ~12 ms / ~17 ms. TinkerOS `savevm` / `loadvm` was 1.25 s / 0.20 s.

## Temple of Hermes guest

This plugin defaults to the official [Temple of Hermes](https://github.com/mojomast/temple-of-hermes) **0.1.2** ISO in the same local, network-off QEMU shape. No guest ISO is bundled. Doctor fetches and SHA-256-verifies:

- URL: `https://github.com/mojomast/temple-of-hermes/releases/download/v0.1.2/TempleOfHermes-0.1.2.ISO`
- SHA-256: `9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13`
- Size: 14,030,848 bytes

The optional Temple of Hermes BBS bridge is separate, host-configured, and off by default (see [Environment](#environment)).

## Architecture

```mermaid
flowchart LR
  U[User] --> P[Desktop pane]
  A[Hermes agent] --> T[Four tools]
  P -->|ctx.rest| B[Plugin backend]
  T --> B
  B -->|QMP VNC COM1 unix| Q[QEMU child]
  Q --> D[qcow2 + pinned ISO]
```

Launch shape (proven):

```text
qemu-system-x86_64 -machine pc,kernel-irqchip=off -accel kvm|tcg
  -cpu qemu64 -m 2G -smp 1 -vga std -display none -nic none
  -qmp unix:…/qmp.sock,server=on,wait=off
  -vnc unix:…/vnc.sock
  -serial unix:…/com1.sock,server=on,wait=off
```

TinkerOS / TempleOS: IDE `-cdrom` + qcow2 `if=ide`. ZealOS: AHCI devices (plain IDE reboots). Contracts: [docs/CONTRACTS.md](docs/CONTRACTS.md). File protocol: [docs/FILES.md](docs/FILES.md).

## Security and disclosures

This is what the code is built to do. Catalog reviewers: this is a **child hypervisor**, not an OS sandbox.

- **Child process.** Spawns `qemu-system-x86_64` with an argument array (no shell). Child env is an exact-name allowlist (`templeos.envsafe.child_env`). No dotenv. No `requires_env`. No secret fallback to `os.environ`.
- **ISO fetch.** Doctor may download the pinned flavor ISO from its official HTTPS URL and refuse a SHA-256 mismatch (partials deleted). Fetches resolve and vet every address, pin the TCP connection (no DNS rebinding), re-check redirects, and disable ambient proxies. QEMU and ISOs are **not** bundled (catalog rule 17).
- **Network.** Guest always `-nic none`. Enabling a fork's networking is not offered.
- **BBS / chat bridge.** Opt-in Temple of Hermes HBBS/1 and chat bridges, off by default. The BBS destination is the literal allow-list name `bbs`; the TLS endpoint comes from host environment or host config, never from guest text. No plaintext fallback. User-configured loopback or private LAN is allowed; metadata, link-local, and CGNAT are refused. Signup claims are stored mode `0600` under plugin data. The optional chat-bridge token is read only through Hermes secret scope. Details: [docs/evidence/BBS-TRANSPORT.md](docs/evidence/BBS-TRANSPORT.md).
- **Hooks.** Companion observer hooks fire on session, LLM, and tool events to animate Terry. They return `None` and do not approve, modify, block, or log other tools or file paths.
- **Sockets.** QMP, VNC, and COM1 are unix sockets under the data dir. Never a LAN VNC port. COM1 stays open for the session or guest bytes are lost.
- **Paths.** Host paths resolve symlinks and stay under `TEMPLEOS_HOME` / plugin data. The data root must not be `/`.
- **Files.** Serial Xfer is capped at 256 KiB. Live RedSea qcow2 is never mounted while QEMU holds it. FAT push is experimental.
- **Desktop.** `@hermes/plugin-sdk` / React only. No `eval`, no `new Function`, no prototype patching, no session-token reads. `ctx.rest` only.
- **Payload budget.** Tool/pane JSON including base64 frames must stay under 512 KiB or returns `payload_too_large`.

## Troubleshooting

| What you see | What it means |
| --- | --- |
| `qemu_missing` | Install `qemu-system-x86_64` and `qemu-img` (see Quickstart). |
| `iso_missing` / `iso_hash_mismatch` | Run `templeos_vm op=doctor`. Delete a bad ISO and re-fetch. |
| KVM reported unusable | `/dev/kvm` exists but cannot be opened. Fix group/udev, or stay on TCG. |
| `serial_not_ready` | Start the VM, keep COM1 open, on TinkerOS run `CommInit;` + `CommInit8n1(1,115200);`, load `Xfer.HC`. |
| ZealOS reboots immediately | Needs AHCI launch flags (flavor `zealos`). Plain IDE is wrong. |
| Debugger screen | `G2;` to continue, `Exit;` to leave, or `templeos_vm op=restore` to `golden`. |
| `agent_paused` | You have Take control, or shared hold-off. Click **Hand back** or wait ~2 s. |
| Pane blank / stale after update | **Capabilities → Plugins → Rescan.** Enable the plugin first. |
| Terry is missing | Companion is off (`companion: off` / `TEMPLEOS_COMPANION=off`), assets were not installed, or **Hide Terry** is active. |
| FAT push `experimental` | Expected. Prefer serial Xfer; bake-off did not see FAT12 as `A:`. |
| Apple Silicon / Windows | Untested. TCG may work; not a supported primary host yet. |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q tests
export PATH="$HOME/.local/node22/bin:$PATH"   # Node 22 for JS tests
node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs
node scripts/build_desktop.mjs --check
python3 evals/measure_schemas.py
```

`evals/measure_schemas.py` prints one integer: o200k tokens of the four tool schemas. This tree measures **972** o200k. The count must stay unchanged (**delta 0**) when docs or tool descriptions change; still four tools, under the ~2,000 budget.

Live QEMU tests are marked `@pytest.mark.smoke` and skipped unless `TEMPLEOS_SMOKE=1` and a pinned ISO already exists. Do not download ISOs in CI by default. The box `/dev/kvm` is often unusable, so smokes run in TCG.

Contracts and pane routes: [docs/CONTRACTS.md](docs/CONTRACTS.md).

## Credits

In memory of **Terry A. Davis** (1969–2018), author of TempleOS. TempleOS is public domain by Terry A. Davis.

The HD Terry companion is **"An original fan tribute with no official TempleOS affiliation."** Its 69 quotes are sourced in [desktop/terry-quotes.json](desktop/terry-quotes.json), with a `source_title` and `source_url` on every entry.

This plugin is not affiliated with Terry's estate, TinkerOS, ZealOS, or Nous Research.

## License

Code is [MIT](LICENSE), © 2026 Kyle Durepos ([mojomast](https://github.com/mojomast)).

TinkerOS and ZealOS are their respective authors' projects; ISOs are fetched from official URLs at runtime and are not redistributed in this repository. QEMU is a system package (GPL/LGPL).
