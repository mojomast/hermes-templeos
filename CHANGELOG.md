# Changelog

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
- Pillow pin `>=10,<12`. Pane screenshots under `docs/images/` and
  `desktop/screenshots/`.
