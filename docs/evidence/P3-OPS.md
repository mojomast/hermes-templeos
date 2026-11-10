# P3 guest operations: daemon RPC, serial modem, lore, and TCG HolyC typing

## Base and lineage

| Item | Value |
| --- | --- |
| Base | `feat/improvements` `99d1b621bc5b0caf00f5463fadd945217b85f05d` |
| Work branch | `feat/p3-guest-ops` |
| P4 input base | `feat/p4-tcg-shift` `750f55559a90fab415b9471fc7b8c0874e56fb37` |
| P5 evidence | `feat/p5-webapp-demo` `53ded9d90fbc631243978efe0504db3e162feba3` |

The base already contains the P4 TCG shifted-key fix. This slice keeps that
per-key input path intact and builds the P5 HolyC speed change on top of it.
Changes are left uncommitted; no branch was switched, merged, tagged, or
force-pushed.

## Tool surface

Exactly four tools remain:

```text
templeos_vm  templeos_screen  templeos_input  templeos_files
```

No fifth tool, no renamed tool, and no new plugin id. P3 adds three ops across
the existing tools and one production typing change inside `op=holyc`.

### `templeos_vm op=modem`

`mode` is `status` (default), `on`, or `off`. The modem is a **COM2 serial
modem**, not a network interface:

- `templeos/flavors.py` records `modem: "com2"` for every flavor and owns the
  process-local modem option.
- When enabled, `socket_args()` adds a second unix `-serial` line next to
  COM1. `-nic none` from `machine_args()` is unchanged, so no NIC, user
  network, tap, bridge, or socket network device is added.
- `assert_airgap()` still passes with the modem line.
- The response reports `transport: "serial"`, `com: 2`, `network: "off"`, and
  whether a restart is needed. It never returns socket paths.
- The option applies to the next `templeos_vm op=start` in the same plugin
  process.

### `templeos_screen op=lore`

Returns static, original operator notes with the prompt shape, `CommInit` /
`CommInit8n1`, Esc-before-typing, debugger recovery (`G2;`, `Exit;`), and
snapshot guidance. It does not contact the guest and is not attributed to
Terry A. Davis.

### `templeos_files op=rpc`

A thin method layer over the existing guest Xfer daemon on COM1. `method` is
`ping`, `stat`, or `version`; `path` is the optional guest path (default
`T:/`).

- `ping` performs a daemon LIST round trip and reports `count`, `protocol`,
  and `elapsed_ms`.
- `stat` returns the same plus the daemon's entries.
- `version` returns the daemon protocol version, magic, and file cap.
- A missing COM1 returns the existing `serial_not_ready` envelope; an unknown
  method returns `invalid_args`.

This reuses the proven framed serial protocol rather than adding a second
transport or tool.

## P5 evidence: HolyC under TCG

The P5 branch (`53ded9d`) recorded that, under TCG, default-speed
`templeos_input op=holyc` garbled characters: `6*7;` became `67;`, and
Shift-quoted text was reordered. Re-running the **same input route** with a
slower per-key path printed `Hello from Hermes` and `42`.

`templeos/input.py` now makes that slower path the default for `op=holyc`
whenever the guest is not on KVM:

- P4's `_send_key_sequential()` remains the TCG key route: each qcode is sent
  down and up as its own QMP event, with the shifted-chord hold and Shift
  release unchanged.
- `op=holyc` selects `TCG_HOLYC_DELAY_S = 0.12` as the inter-key gap (capped at
  0.30 s). The existing per-character hold is still applied by the P4 path.
- KVM keeps the previous fast path (`<= 0.05 s` inter-key gap).
- The `type_delay_s == 0` unit-test seam stays instantaneous, so unit tests
  remain fast.
- The result envelope now reports `delay_s`, `accel`, and `per_key` so the
  caller can see whether the slow route was used.

No echo-scraping fallback is needed: the slow per-key route is the default on
TCG. `via=serial` is unchanged and still only selected when the guest has
initialized `Comm*`.

## Tests

| Check | Command | Result |
| --- | --- | --- |
| Python suite, no live guest | `python3 -m pytest -q tests` | 150 passed, 4 skipped |
| P3/P4/Tools focused | `python3 -m pytest -q tests/test_contracts.py tests/test_tools.py tests/test_input.py` | 28 passed |
| Live TCG smoke | `TEMPLEOS_SMOKE=1 TEMPLEOS_ISO=<pinned ISO> python3 -m pytest -q tests/test_live_tools_smoke.py -s` | 1 passed in 172 s |
| Desktop JS | `node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs` | 22 passed |
| Desktop bundle | `node scripts/build_desktop.mjs --check` | up to date |
| Schema measure | `python3 evals/measure_schemas.py` | `972` |

### TCG smoke details

QEMU 8.2.2, `-accel tcg -display none -nic none -machine
pc,kernel-irqchip=off`; TinkerOS 5.20-rc10 with the pinned SHA-256
`feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4`.

The smoke booted the guest, checked `templeos_vm op=modem mode=status`
(`transport=serial`, `network=off`), read `templeos_screen op=lore`, and typed
`"Hello from Hermes\n"; 6*7;` through `templeos_input op=holyc`. The response
reported `accel=tcg`, `per_key=true`, and `delay_s>=0.12`; glyph OCR read back
`Hello from Hermes` and `ans=0x0000002A=42`. No QEMU process was left behind.

## Schema growth

| Measure | o200k tokens |
| --- | --- |
| Before (base `99d1b…`) | 892 |
| After (P3) | 972 |
| Delta | +80 (+9.0%) |

The growth is the three op names plus the small `mode` and `method` enums and
short descriptions. It stays far under the ~2,000 budget and adds no fifth
tool.

## P4 regression guard

- `_accel`, `_shifted_chord`, `_send_key_sequential`, `_send_key`,
  `_input_events`, and `_unstick_shift` were not rewritten.
- `tests/test_input.py` still covers the shifted chord down/hold/up order.
- New tests cover the TCG slow `op=holyc` route, KVM fast route, and the
  zero-delay seam.
- The live smoke typed the shifted one-liner and read back both strings.

## Files changed

```text
templeos/tools.py
templeos/flavors.py
templeos/input.py
tests/test_tools.py
tests/test_input.py
tests/test_live_tools_smoke.py
docs/evidence/P3-OPS.md
```

No secrets, tokens, tailnet addresses, or host-specific home/workspace/profile
paths are included in this report or the patch.

## Open issues

- The modem is a COM2 serial modem for guest `Comm` drivers; it is not an
  Ethernet NIC. Enabling a fork's IP stack remains out of scope (`-nic none`).
- The modem option is process-local and applies to the next start; a running
  guest needs a restart.
- `templeos_files op=rpc` uses the existing LIST daemon method, so `stat` needs
  the same `Xfer.HC` helper as `list`/`pull`/`push`.
