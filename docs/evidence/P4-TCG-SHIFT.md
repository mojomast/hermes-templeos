# P4 TCG shifted-key evidence

## Environment

- QEMU: `QEMU emulator version 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)`
- Accelerator: `-accel tcg` (TCG only; no KVM in this sandbox)
- Machine: `pc,kernel-irqchip=off`, `-display none`, `-nic none`
- Guest: TinkerOS 5.20-rc10
- ISO SHA-256: `feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4`

## Failure

Under slow TCG, a batched QMP `input-send-event` chord could reach the guest
after Shift was already released. `Shift+apostrophe` was delivered as a bare
apostrophe, so the HolyC one-liner `"Hello from Hermes\n"; 6*7;` became invalid
(or printed the wrong text), and `Shift+8` arrived as an unshifted `8`.

While probing the live guest, the asynchronous `send-key` hold also reordered
some plain characters, so the production slow path now uses deterministic
per-key QMP events instead of overlapping `send-key` timers.

## Production fix (`templeos/input.py`)

- `_accel(qmp)` reads the live VM accelerator (`tcg`, `kvm`, ...).
- On fast hosts (`kvm`) and on the zero-hold unit-test seam, the existing
  down/up event path is unchanged.
- On non-KVM accelerators with a real hold, `_send_key` uses
  `_send_key_sequential`: every key goes down in order, the chord is held, then
  every key goes up in reverse order.
- Shifted chords use an adaptive hold of at least 120 ms (capped at 300 ms);
  plain keys use a short 20-60 ms hold. A final Shift release is always sent.
- This is the normal production code path. No test monkeypatches
  `_send_key`, `input-send-event`, or `send-key`.

## Test changes

- `tests/test_api.py`: the `test_router_mounts_when_fastapi_is_available`
  click lambda now accepts `**kwargs`, so it tolerates the `settle_s`/`hold_s`
  keywords that `templeos/api.py` passes to `templeos.input.click`.
- `tests/test_live_tools_smoke.py`:
  - ISO lookup is sandbox-portable: `TEMPLEOS_ISO`, then
    `doctor.ensure_iso(..., fetch=False)`, then `$TEMPLEOS_HOME/isos/`, then
    the legacy bake-off location.
  - Boot waits for a real `T:/Home>` prompt before typing, so a blank early
    TCG frame cannot race the input.
  - Types the one-liner through `templeos_input` with `op=holyc`, `via=type`,
    then reads the screendump with the built-in 8x8 glyph matcher.
  - Asserts a real output line `Hello from Hermes` plus the evaluated result
    `ans=0x0000002A=42` (not the echoed source or a menu address), retrying a
    garbled TCG line at the prompt up to three times.
  - Saves the frame to `shots/p4-tcg-shift/hello-from-hermes.png`.

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Full pytest with live smoke | `TEMPLEOS_SMOKE=1 python3 -m pytest -q tests` | 131 passed, 3 skipped |
| Full pytest without live smoke | `python3 -m pytest -q tests` | 130 passed, 4 skipped |
| JS pane tests | `node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs` | 16 passed, 0 failed |
| Desktop bundle | `node scripts/build_desktop.mjs --check` | `desktop/plugin.js is up to date` |
| Schema measure | `python3 evals/measure_schemas.py` | `892` (unchanged) |
| Tool surface | four handlers | `templeos_files`, `templeos_input`, `templeos_screen`, `templeos_vm` |

The live smoke boots TCG, waits for the prompt, types the one-liner through the
production input path, verifies both expected strings by glyph OCR, saves the
PNG, and then completes the existing snapshot/restore, pane API, and cleanup
checks. QEMU is stopped at the end of the run.
