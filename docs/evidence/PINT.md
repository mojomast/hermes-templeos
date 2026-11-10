# PINT — plugin integration evidence

Base: `feat/improvements` at `99d1b621bc5b0caf00f5463fadd945217b85f05d`
(Terry already merged there by Kyle at `99d1b62`).
Accepted Terry heads: `feat/terry-big` `c944fc27800263e2600e2bf2d4914ea6060b5299`
(huge default size) and `feat/terry-v4` `f2b7a60c0c2d9235a60dce969f8333aaf120526f`
(high-res v4 rig at BIG size).

All integration changes are **uncommitted** in the working tree, ready for the
launcher's `git diff HEAD` collection.

## Sandbox branch reality

This sandbox contains a single snapshot commit (`488e3e3`, message
`base 99d1b621bc5b0caf00f5463fadd945217b85f05d`), no remotes, and only
`master`. The snapshot tree is the `99d1b62` integration base. Switching or
creating branches is prohibited by the task, so the patch is applied directly
on this tree; there is no `feat/plugin-integration` ref in this sandbox.

No `feat/p4-tcg-shift`, `feat/p3-guest-ops`, `feat/bbs-transport`,
`feat/bbs-skill`, `feat/terry-big`, or `feat/terry-v4` refs exist here either.
Their accepted code is present in the base tree and was not re-merged from
scratch (in particular, `feat/terry-p2` was **not** re-merged and `04bd074`
was **not** used as a starting point).

## Integration matrix

| Item | Commit | State on this tree |
| --- | --- | --- |
| Base (P1/P2/Terry/P4) | `99d1b621bc5b0caf00f5463fadd945217b85f05d` | snapshot tree |
| P1 pane/API + four-tool contract | in base | verified by `tests/test_contracts.py`, `tests/test_api.py`, and the live pane route smoke |
| Terry BIG | `c944fc27800263e2600e2bf2d4914ea6060b5299` | inherited through `99d1b62`; huge default size, no re-merge |
| Terry v4 rig | `f2b7a60c0c2d9235a60dce969f8333aaf120526f` | inherited through `99d1b62`; high-res v4 rig at BIG size |
| P2 theme | `15b74799cef80d60a5aad8061d2c2203e5589a21` | in base; see `P2-THEME.md` / `TERRY-P2.md` |
| P4 TCG shift | `750f55559a90fab415b9471fc7b8c0874e56fb37` | in base; see `P4-TCG-SHIFT.md` |
| P3 guest ops (holyc TCG) | `feat/p3-guest-ops` `a197b02a26aa35ebb04a840d207d37d4bc0aab89` | ref absent; production fix applied here, with test |
| P5 webapp evidence | `feat/p5-webapp-demo` `53ded9d` | cited; P5 stays parked until a model credential is provided |
| BBS transport | `feat/bbs-transport` | ref absent in this sandbox; not integrated |
| BBS skill | `feat/bbs-skill` | ref absent in this sandbox; not integrated |
| Chat bridge | — | new `templeos/chat_bridge.py`; see `PINT-CHAT-BRIDGE.md` |

Terry remains docked to the right of the guest pane with the P2 Hermes theme
and the P4 input path. No Terry quotes were invented and PR #3 was not touched.

## P4 TCG shifted-key fix (already in base)

`templeos/input.py` carries the production slow-TCG path:

- `_accel()` reads the live accelerator;
- `_send_key_sequential()` sends one QMP key event per down in order, holds,
  then releases in reverse order;
- shifted chords use an adaptive 120–300 ms hold, plain keys 20–60 ms;
- KVM and the zero-hold unit seam keep the existing batched path.

`tests/test_api.py::test_router_mounts_when_fastapi_is_available` stubs
`templeos.input.click` with a lambda that accepts `**kwargs`, so the
`settle_s`/`hold_s` keywords passed by `templeos/api.py` are accepted. No test
monkeypatches `_send_key` or the QMP input commands.

## P3 HolyC TCG typing fix (applied here)

`feat/p3-guest-ops` was not available as a ref. The production fix is applied
in `templeos/input.py`:

- `HOLYC_TCG_DELAY_S = 0.09`, `HOLYC_MAX_DELAY_S = 0.12`;
- `_typing_delay(rt, accel)` keeps the zero-delay unit seam, keeps KVM at the
  old ≤50 ms cap, and gives non-KVM accelerators a ≥90 ms per-key cadence;
- `holyc(..., via=type)` returns `accel`, `key_delay_s`, and `tcg_slow` so a
  caller can see which cadence ran;
- combined with the P4 per-key event path, no shifted chord is batched under
  TCG.

Test: `tests/test_input.py::test_holyc_tcg_types_slower_per_key` types
`"Hello from Hermes\n"; 6*7;` through `holyc` with a TCG fake, asserts the
slower cadence, asserts Shift is never batched with its key, and asserts the
adaptive hold. It is offline and does not touch QEMU.

P5 evidence (`feat/p5-webapp-demo` `53ded9d`) showed default-speed HolyC
garbling under TCG, while the slower per-key path printed `Hello from Hermes`
and `42`. That is the cadence adopted here.

## Chat bridge

`templeos/chat_bridge.py` lets the host `hermes_chat_relay.py` `ChatResponder`
call `reply(text)` and forward one finished reply to a Hermes agent. Enablement,
endpoint, token, and timeout come from `TEMPLEOS_CHAT_BRIDGE*` environment
variables or an explicit config object; nothing is hardcoded and no fifth tool
is registered. When disabled or no agent is available the bridge raises a typed
error (`ChatBridgeDisabled` / `ChatBridgeUnavailable`) or `try_reply` returns
`None`, so the relay falls back to its offline `HermesResponder`.

Contract, wire format, and relay snippet: `docs/evidence/PINT-CHAT-BRIDGE.md`.
Tests: `tests/test_chat_bridge.py` (offline fake transport plus an ephemeral
loopback HTTP server).

## Verification

| Check | Command | Result |
| --- | --- | --- |
| Full pytest, live smoke | `TEMPLEOS_SMOKE=1 TEMPLEOS_ISO=isos/TinkerOS_5.20-rc10.ISO python3 -m pytest -q tests` | **153 passed, 3 skipped** |
| Offline pytest | `python3 -m pytest -q tests` | 152 passed, 4 skipped |
| New input test | `python3 -m pytest -q tests/test_input.py` | 12 passed |
| New chat bridge tests | `python3 -m pytest -q tests/test_chat_bridge.py` | 10 passed |
| Live smoke (after the P3 change) | boot TCG, wait for `T:/Home>`, type the one-liner through `templeos_input op=holyc via=type`, glyph-read the screendump | `Hello from Hermes` and `ans=0x0000002A=42`; the run wrote `shots/p4-tcg-shift/hello-from-hermes.png`, which is not part of this patch |
| JS pane tests | `node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs` | 22 passed, 0 failed |
| Desktop bundle | `node scripts/build_desktop.mjs --check` | `desktop/plugin.js is up to date` |
| Schema measure (o200k) | `python3 evals/measure_schemas.py` | **892** (delta 0) |
| Tool surface | `templeos.tools.TOOL_NAMES` | four: `templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files` |

ISO used for the live run: public TinkerOS 5.20-rc10, SHA-256
`feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4`.
QEMU was TCG only (`-accel tcg`, no KVM), with the sandbox QEMU 8.2.2.

## Safety

- No secrets, tokens, tailnet addresses, home/workspace paths, or BBS hostnames
  are recorded here or committed.
- No QEMU ISO, disk, socket, or runtime state is added to the tree (ignored).
- No commit, branch switch, stash, tag, force-push, or deploy was performed.
- No Hermes keys were read from the host.

## Open items

- `feat/bbs-transport` and `feat/bbs-skill` are not present in this sandbox, so
  their TLS-from-config transport and agent skill are not in this patch. They
  need a follow-up integration run where those refs exist.
- The accepted branch refs are absent locally; their shared ancestors were
  verified through the base tree, docs, and tests rather than `git merge`.
- P5 remains parked until Kyle supplies a model credential; this patch only
  cites its TCG evidence.
