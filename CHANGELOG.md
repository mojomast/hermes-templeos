# Changelog

## Unreleased
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
