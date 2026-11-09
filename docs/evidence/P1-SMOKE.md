# P1 live smoke evidence

## Environment

- QEMU: `qemu-system-x86_64` 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)
- Acceleration: `accel=tcg` (no KVM in the sandbox)
- Machine: `pc,kernel-irqchip=off`, `-display none`, `-nic none`
- Guest: TinkerOS 5.20-rc10
- ISO SHA-256: `feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4`

The live test resolves the ISO from `TEMPLEOS_ISO`, then the plugin ISO cache
(`$TEMPLEOS_HOME/isos/` / doctor `ensure_iso`), then the legacy bake-off path.
The pinned SHA-256 is still checked before boot.

## Live tool-level smoke

`tests/test_live_tools_smoke.py` was run with `TEMPLEOS_SMOKE=1` and passed.
It was not skipped. The test drove the four registered tools
(`templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files`) plus the
pane API.

Typed HolyC one-liner:

```holyc
"Hello from Hermes\n"; 6*7;
```

Guest readback after the one-liner:

```text
T:/Home>"Hello from Hermes\n"; 6*7;
Hello from Hermes
0.000017s ans=0x0000002A=42
```

- `Hello from Hermes`: visible
- `42`: visible (`ans=0x0000002A=42`)

Screenshot: `shots/p1-smoke/hello-from-hermes.png`

QEMU was stopped at the end; no `qemu-system-x86_64` process was left running.

## Test and schema results

- Python: `TEMPLEOS_SMOKE=1 python3 -m pytest -q tests` -> **130 passed, 3 skipped, 1 failed**.
  The failure is the pre-existing `tests/test_api.py::test_router_mounts_when_fastapi_is_available`
  mismatch: the test replaces `templeos.input.click` with a lambda that does not
  accept the `settle_s`/`hold_s` keywords that `templeos/api.py` passes. It is
  unrelated to this smoke and is in an unassigned file.
- JS: `node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs`
  -> **16 passed, 0 failed, 0 skipped**.
- Desktop bundle: `node scripts/build_desktop.mjs --check` -> `desktop/plugin.js is up to date`.
- Schemas: `python3 evals/measure_schemas.py` -> **892 o200k tokens**
  (baseline 825, +67). Four tools only; no fifth tool was added. No schema
  change was made in this task, so before/after are both 892.

## Sandbox note

This sandbox runs the guest under TCG only. The live test keeps the real
`templeos_input op=holyc` path but substitutes QMP `send-key` with a longer
hold for the test session because the batched `input-send-event` chord path
drops shifted characters on this slow TCG guest. The same one-liner then
renders correctly in the guest and the screenshot above.

## Web app gap

The full Hermes web app UI demo (gateway chat plus dark-mode TempleOS pane)
was not attempted here: this sandbox has no running Hermes web app/gateway or
browser session. The tool-level live smoke and the pane API checks in the same
test were completed. Remaining web app work is the browser/chat demonstration
described in `docs/bees/plugin-webapp-demo.md`.
