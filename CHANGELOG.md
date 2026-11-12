# Changelog

## 0.2.2

- Fix `templeos_vm op=bbs_digest` against the live community BBS: the compact
  digest is now the additive HBBS/1 section 17.2 `LIST` action `digest`
  instead of a top-level `DIGEST` command, so Temple of Hermes v0.1.3 no
  longer answers `unknown_command`. An optional `cursor` is forwarded and no
  `limit` is sent on the wire.
- `_normalize_digest` reads `mail.unread`, `mentions.pending`, and
  `replies.count` plus the latest arrays into the existing compact
  counts/ids/subjects/pending envelope, and still accepts the older flat
  counts/ids/subjects fixture. A server without the extension returns an
  empty compact result instead of crashing. Tokens, bodies, and full server
  payloads are never returned or logged.

## 0.2.1

- Ship the public community Temple of Hermes BBS (HBBS/1, Temple of Hermes
  v0.1.3) built in at `tls://toh.rizz.click:9443` and enabled by default.
  Agents no longer probe DNS, ports, vhosts, or certificate names. Opt out
  with `bbs.json` `{"enabled": false}` or `TOH_BBS_ENABLED=0`; a human may
  still override the endpoint via `bbs.json` or `TOH_BBS_ENDPOINT`. Guests
  still cannot choose a host or port; the only destination name is `bbs`.
- Add `templeos_vm op=bbs_join` (aliases `join`, `bbs_setup`): sign up the
  human first, then the agent under that human, persist mode-0600 credentials
  under `$TEMPLEOS_HOME/bbs/`, and stay idempotent via AUTH refresh. Tokens
  never appear in tool output, pane UI, logs, or errors.
- Populate `status.bbs` and update the pane BBS chip; add a Join BBS button
  (and a small on/off toggle). Digest and codeshare authenticate with the
  stored agent credentials on every connection and return a
  `run templeos_vm op=bbs_join` hint when not joined.
- Update `hermes-bbs`, `temple-session`, and `templeos-operator` skills plus
  transport/community-ops evidence for the built-in BBS and light 2-session
  cadence.
- Detect a colliding `qemu-system-x86_64` wrapper in doctor, skip it when a
  real QEMU is later on PATH (so preinstalled-disk boot is not stolen by a
  wrapper `-drive ...index=0`), and include a sanitized `qemu.log` tail in
  start errors when QEMU exits immediately instead of only reporting
  `QMP connect failed`.
- `bbs_join` adopts existing `$TEMPLEOS_HOME/bbs/human-<account>.json` and
  `agent-<account>.json` (raw AUTH JSON, mode 0600) as well as legacy
  `human.creds` / `agent.creds` / `token.txt`, so a host that already signed
  up is not asked to sign up again. AUTH `rate_limited` waits for
  `retry_after` (capped at 60 s) and retries once.

## 0.2.0

- Default guest is Temple of Hermes 0.1.3, pinned to the official GitHub
  release ISO (`TempleOfHermes-0.1.3.ISO`, SHA-256
  `fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd`,
  14,053,376 bytes): HermesDaemon structured file errors and the guest home
  journal (`C:/Home/<handle>/`).
- Temple of Hermes boots a preinstalled disk image by default (local `C:`
  storage). `TempleOfHermes-0.1.3-disk.qcow2` (SHA-256
  `d81a3c189093bd0edddad50b7a55d6582d0490204d63720e14fc5fb9d901f1aa`,
  11,107,840 bytes) is downloaded once from the v0.1.3 release on doctor
  setup or first start, verified, and booted through a copy-on-write overlay.
  A failed download or verification falls back to the live ISO. Turn it off
  with `disk_image: "off"` or in the pane; `disk_image_path` can point to a
  local copy.
- Community ops on the existing four tools (no new tool): `session_start`,
  a compact BBS digest, HolyC codeshare fetch (VM-only, 32 KiB / 15 s caps,
  written under `C:/Home/<handle>/Src/`), and a pending-only nudge hook (max
  2/day; `nudge` setting or `TEMPLEOS_NUDGE` turns it off). Tool schema
  o200k 1045 -> 1201.
- Bundled `temple-session` skill (default cadence 2 sessions/day) and a
  token-budget eval.
- Steer agents to the four `templeos_*` tools when Hermes Tool Search defers them: a system prompt section, skill v0.1.2, and tool descriptions require `tool_search`/`skill_view` and forbid VNC/socket workarounds. Prefer `templeos_input op=holyc` for HolyC one-liners. `register()` also installs pane agent-log hooks.
- `templeos_vm op=start` (and other running-VM ops) reattach QMP/COM1 if QEMU is still alive after a gateway restart, instead of returning `vm_already_running` with no in-process binding.
- holyc `via=auto` types at the prompt unless `Runtime.guest_serial_ready` (host COM1 open no longer selects serial; silent drop fixed).
- Modifier chords (e.g. `"`) use QMP `input-send-event` down, a short hold, then up so TinkerOS TCG does not turn Shift+apostrophe into `'`.
- Pane `/frame` served from a background frame cache (≤5 fps, no OCR on the
  request path) so the Hermes gateway is not starved while the pane is open.
- Pane polling capped (~4–5 fps visible; backs off when idle, hidden, or slow).
  Aborted fetches no longer show "signal is aborted without reason".
- `/input` uses zero type-delay and short click settle/hold for pane events.
- First-boot Install/Tour prompts auto-dismissed after ISO `start` (Esc then n).
- Pillow pin widened to `>=10,<14` (Hermes PM may ship Pillow 13).
- ZealOS glyph table expanded from the holyc-prompt fixture (~0.63 confidence).

## 0.1.1

- Default flavor is Temple of Hermes 0.1.2 (`templeoh` / `temple-of-hermes`),
  pinned to the official GitHub release ISO (`TempleOfHermes-0.1.2.ISO`,
  SHA-256 `9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13`,
  14,030,848 bytes). TinkerOS 5.20-rc10, TempleOS 5.03, and ZealOS stay
  selectable.
- The Desktop pane has a visible Guest OS picker (version + SHA state). The
  choice persists through `GET`/`POST /settings` (`ctx.rest`) and
  `templeos_vm op=flavor`. A missing ISO is fetched on the pinned-SHA path;
  a running guest switches on the next boot, with a Reboot now control.

## 0.1.0

- First integrated release: TinkerOS VM, screen/input, Desktop pane, and files.
- Four composable tools (`templeos_vm`, `templeos_screen`, `templeos_input`,
  `templeos_files`), JSON envelopes, path confinement, env allowlist, flavor
  pins, and a shared/watch/user input arbiter.
- Slice A: QEMU lifecycle, QMP, COM1, doctor (pinned ISO + SHA-256). Start
  binds `templeos.screen` and exposes `vm.get_runtime()` / `vm.get_serial()`.
- Slice B: PNG look, 8×8 glyph `read_text`, QMP type/click/move/HolyC.
  Unbound ops return `vm_not_running`. Live clicks settle and hold ~150 ms
  when `type_delay_s > 0`.
- Slice C: Desktop pane (`ctx.rest` only) plus pane API routes including
  `/vm`, `/start`, `/stop`, `/reset`, `/snapshots`, `/log`, `/doctor`,
  `/setup`. `/frame` supports `?since` and `If-None-Match` (`{unchanged:true}`).
- Slice D: serial framed file protocol (`TXFR`, 256 KiB cap) with HolyC
  helper `skills/templeos-operator/guest/Xfer.HC`, experimental stopped-VM
  FAT push, operator skill, README, catalog draft, and `docs/FILES.md`.
  Empty COM1 returns `serial_not_ready`.
- Pillow pin `>=10,<14` (was `<12` at 0.1.0 freeze). Pane screenshots under `docs/images/` and
  `desktop/screenshots/`.
