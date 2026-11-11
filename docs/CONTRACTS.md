# TempleOS plugin contracts

Slice 0 freeze. Later slices implement the stubs against this document.
Integration branch: `feat/integration` (never push straight to `main`).

Plugin id: `templeos`. Display name: TempleOS. Version: `0.1.0`.
`requires_hermes: ">=0.23.0"`. Skill id: `templeos:templeos-operator`.
Default flavor: TinkerOS 5.20-rc10. Optional: `templeos` (stock 5.03) and
`zealos` (AHCI, 1024×768). Network always off (`-nic none`).

## LEASES

Pattern: each slice owns only its leased paths. Touching anything else is out
of scope and will be rejected. Shared contracts (`templeos/tools.py`,
`tests/fakes.py`, and the LEASES table in this file) stay on
`feat/integration`. Slices may **add tests only in their own test files**.
Do not edit another slice's files. Do not force-push, rewrite history, or
push to `main`. Do not deploy anywhere. Do not spend. Secret-scan before
every push; never print secrets or tokens.

Integration branch that later slices branch from: `feat/integration`.

| Slice | Branch | May edit (exclusive) | Import only (do not edit) |
|---|---|---|---|
| A — VM lifecycle, QMP, serial, qemu, doctor | `feat/vm` | `templeos/qemu.py`, `templeos/qmp.py`, `templeos/serial.py`, `templeos/vm.py`, `templeos/doctor.py`, `tests/test_vm.py`, `tests/test_qmp.py`, `tests/test_serial.py`, `tests/test_qemu.py`, `tests/test_doctor.py` | `templeos/tools.py`, `templeos/flavors.py`, `templeos/paths.py`, `templeos/envsafe.py`, `templeos/arbiter.py`, `tests/fakes.py`, this LEASES table |
| B — screen + input | `feat/screen-input` | `templeos/screen.py`, `templeos/input.py`, `tests/test_screen.py`, `tests/test_input.py`, `tests/fixtures/glyphs/**`, `tests/fixtures/frames/**` | same, plus Slice A modules once merged or stacked |
| C — desktop pane + api | `feat/pane` | `templeos/api.py`, `dashboard/**`, `desktop/**`, `scripts/build_desktop.mjs`, `tests/test_api.py`, `tests/js/**` | same; pane talks only through `ctx.rest` |
| D — files + skill + README + catalog draft + docs | `feat/files-docs` | `templeos/files.py`, `skills/**`, `README.md`, `CHANGELOG.md`, `docs/catalog/**`, `docs/**` except the LEASES table in this file, `tests/test_files.py` | same |

**Integration-owned (do not edit without coordinating on feat/integration):**
`plugin.yaml`, `pyproject.toml`, `__init__.py`, `templeos/__init__.py`,
`templeos/tools.py`, `templeos/paths.py`, `templeos/envsafe.py`,
`templeos/flavors.py`, `templeos/arbiter.py`, `tests/fakes.py`,
`tests/test_plugin.py`, `tests/test_plugin_yaml_strict.py`,
`tests/test_contracts.py`, `tests/test_paths.py`, `tests/test_envsafe.py`,
`tests/test_flavors.py`, `tests/test_arbiter.py`, `tests/test_tools.py`,
`tests/test_fakes.py`, `tests/test_security.py`, `tests/test_stubs.py`,
`evals/measure_schemas.py`, and this LEASES table.

If a slice needs a new error code, a schema change, or a Pillow / other pin,
open a note against integration rather than editing `tools.py` or
`pyproject.toml`. Schema budget: keep the four tools under about 2,000
o200k tokens (`python3 evals/measure_schemas.py`).

## Verify commands (every slice)

Run from the repo root, with this repo on `PYTHONPATH` (or `pip install -e .`)
and the `dev` extra installed (`fastapi`, `httpx`, `pytest`, `pyyaml`,
`ruamel.yaml`, `tiktoken`):

```bash
python3 -m pytest -q tests
node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs
node scripts/build_desktop.mjs --check
python3 evals/measure_schemas.py
```

Live QEMU tests must be marked `@pytest.mark.smoke` and skipped unless
`TEMPLEOS_SMOKE=1` and a pinned ISO already exists on disk. Do not download
ISOs in CI by default.

Optional additional files a slice adds (for example `tests/test_vm.py`) are
picked up by the same `pytest` command. A slice must leave the integration
tests green.

## JSON envelope

Every registered tool handler returns a **string**: `json.dumps(envelope)`.
Shape:

```json
{"ok": true,  "error": null, "code": null, "fix": null, "...": "..."}
{"ok": false, "error": "human message", "code": "agent_paused", "fix": "what to do"}
```

Helpers: `templeos.tools.ok`, `templeos.tools.err`, `templeos.tools.not_implemented`.
The whole serialized JSON, including base64 frames, must stay under
`MAX_ENVELOPE_BYTES` (512 KiB). Oversize results become `payload_too_large`.

### Error codes

| code | When |
|---|---|
| `not_implemented` | Slice has not landed this op yet |
| `invalid_op` | Unknown `op` |
| `invalid_args` | Missing or illegal arguments |
| `agent_paused` | User has control, or shared-mode hold-off (~2 s) |
| `watch_only` | User tried to type while the pane is in watch mode |
| `path_escape` | Host path left the plugin data dir, or `TEMPLEOS_HOME` is `/` |
| `unknown_flavor` | Not `tinkeros`, `templeos`, or `zealos` |
| `vm_not_running` | Need `templeos_vm op=start` |
| `vm_already_running` | Start called while a VM is up |
| `qemu_missing` | `qemu-system-x86_64` not on PATH |
| `iso_missing` | Pinned ISO not on disk |
| `iso_hash_mismatch` | Fetched or cached ISO failed SHA-256 |
| `snapshot_failed` | `savevm` failed (often a writable raw floppy) |
| `restore_failed` | `loadvm` failed; send `cont` if the VM is paused |
| `serial_not_ready` | COM1 not open, or Comm* not initialized |
| `timeout` | `wait_idle` (or similar) timed out |
| `payload_too_large` | Envelope exceeded 512 KiB |
| `doctor_failed` | Doctor checks failed |

## Tools

Four tools only. Names must stay in sync with `plugin.yaml` `provides_tools`.

### `templeos_vm`

Ops: `start` `stop` `reset` `snapshot` `restore` `status` `doctor`.

- `flavor`: `tinkeros` (default), `templeos`, `zealos`.
- `name`: snapshot id for `snapshot`/`restore` (default `golden`). Simple
  identifier only; no slashes or `..`.
- `start` attaches a writable qcow2 even in live-CD mode, opens COM1 and
  keeps it open, prefers `loadvm golden` when present, else boots the ISO.
- `snapshot` ejects non-qcow2 writables first.
- `restore` issues `cont` if `loadvm` leaves the VM paused (including a
  failed `loadvm`, which stays in `restore-vm`).
- `status` may list socket **existence** only, never socket contents or tokens.
- `doctor` reports QEMU path/version, whether `/dev/kvm` can be **opened**,
  ISO pin presence and hash, disk path existence. It does not install packages.

### `templeos_screen`

Ops: `look` `read_text` `wait_idle` `hash`.

- `look` returns a PNG (not JPEG): `mime`, `width`, `height`, `data` (base64),
  `sha256`, short `caption`.
- `read_text` prefers serial when COM1 is already connected, else 8×8 glyphs.
- `wait_idle` / `hash` use `flavors.hash_crop`; full-frame hashes never stabilize.
- `timeout_s` is for `wait_idle` (default 5, max 120).

### `templeos_input`

Ops: `type` `keys` `click` `move` `holyc`.

- `type` needs `text`. `keys` needs a non-empty `keys` array of QEMU qcodes.
- `click`/`move` need integer `x`, `y`. `button` is `left|right|middle`.
- `via` for pointer: `auto|vmmouse|msset|relative`. `auto` uses
  `flavors.mouse_strategy` (TinkerOS: vmmouse absolute; stock: MsSet;
  ZealOS: relative). Absolute QMP events error on stock TempleOS and ZealOS.
- `holyc` needs `text` (source), cap `HOLYC_MAX_BYTES` (64 KiB). `via` may be
  `auto|serial|type`. On TinkerOS, CommInit is disabled at boot; call
  `CommInit;` then `CommInit8n1(1,115200);` before `CommPutS`.
- The handler takes the arbiter queue and returns `agent_paused` when the
  user is driving or the shared hold-off is active.

### `templeos_files`

Ops: `list` `pull` `push`.

- `path` is a **guest** path (default `T:/` for list).
- `dest` (pull) and `src` (push) are **host** paths, confined under
  `templeos.paths.home()` before the files module is called.
- Never mount the live RedSea qcow2 while QEMU has it open.

## Module APIs

Typed signatures and docstrings live in the modules themselves. Summary:

| Module | Functions / types | Slice |
|---|---|---|
| `templeos.qemu` | `build_argv`, `spawn`, `terminate`, `is_running` | A |
| `templeos.qmp` | `QMPClient.connect/close/cmd/hmp/screendump/send_key/input_send_event` | A |
| `templeos.serial` | `SerialPort.open/close/write/read/read_available` | A |
| `templeos.vm` | `start`, `stop`, `reset`, `snapshot`, `restore`, `status`, `get_runtime`, `get_serial` | A |
| `templeos.doctor` | `kvm_usable`, `qemu_version`, `ensure_iso`, `doctor` | A |
| `templeos.screen` | `look`, `read_text`, `wait_idle`, `frame_hash`, `glyph_read` | B |
| `templeos.input` | `type_text`, `send_keys`, `click`, `move`, `holyc` | B |
| `templeos.files` | `list_guest`, `pull`, `push` | D |
| `templeos.flavors` | pins, `machine_args`, `disk_args`, `socket_args`, `assert_airgap` | integration |
| `templeos.paths` | `home`, `confine`, `ensure_layout`, `socket_paths` | integration |
| `templeos.envsafe` | `child_env`, `CHILD_ENV_ALLOWLIST` | integration |
| `templeos.arbiter` | `Arbiter`, `get_arbiter`, `reset_arbiter` | integration |

`qemu.spawn` **must** pass `env=child_env(...)`. Do not inherit `os.environ`.
`doctor.kvm_usable` must open `/dev/kvm`, not only `exists()`.
`doctor.ensure_iso` fetches only the official URL in `flavors.py` and
verifies the pinned SHA-256, deleting partials on mismatch.

Proven launch fragments (also in `flavors.py`):

```text
qemu-system-x86_64 -machine pc,kernel-irqchip=off -accel tcg|kvm
  -cpu qemu64 -m 2G -smp 1 -vga std -display none -nic none
  -qmp unix:PATH,server=on,wait=off
  -vnc unix:PATH
  -serial unix:PATH,server=on,wait=off
```

TinkerOS / TempleOS disks: `-cdrom ISO -boot order=d,menu=on`
`-drive file=DISK.qcow2,format=qcow2,if=ide,index=1,media=disk`.

ZealOS (AHCI required):

```text
-device ahci,id=ahci
-drive file=ISO,if=none,id=cdrom,media=cdrom,readonly=on,format=raw
-device ide-cd,drive=cdrom,bus=ahci.0,bootindex=1
-drive file=DISK.qcow2,if=none,id=hd,format=qcow2
-device ide-hd,drive=hd,bus=ahci.1
```

ISO pins (SHA-256):

| Flavor | Filename | SHA-256 |
|---|---|---|
| tinkeros | `TinkerOS_5.20-rc10.ISO` | `feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4` |
| templeos | `TOS_Distro.ISO` | `3c68ca395d0b64f779f1ffa330e2685798b17862e3c36ae4e349537fd676b40b` |
| zealos | `ZealOS-PublicDomain-BIOS-2025-11-10-02_56_42.iso` | `a9c283d79af5938f053cc342666fdea8eeaeb2a2675f3e868aae0cbfad1d1bf0` |

URLs and MD5s are in `templeos/flavors.py`. Do not use Internet Archive as
the install source.

## Backend REST (pane)

Mounted at `/api/plugins/templeos/` by `dashboard/manifest.json` →
`dashboard/plugin_api.py` → `templeos.api.router`. The iframe must not dial
`127.0.0.1`, must not read tokens from parent storage, and must not load
remote scripts. `ctx.rest` only. Hermes `>= 0.23.0`.

| Method | Path | Body / query | Result |
|---|---|---|---|
| GET | `/health` | | `{ok, plugin, version, mode, agent_paused}` |
| GET | `/status` | | health + `running, flavor, accel, snapshot, kvm, sockets, mode, ...` |
| GET | `/frame` | `?since=<sha256>` or `If-None-Match` | PNG `{ok, mime, data, width, height, sha256, caption}`. If the hash matches, HTTP 200 with `{unchanged: true, data: null, sha256}` (not 304). |
| GET | `/control` | | `{ok, mode, agent_paused, hold_off_s, user_may_input}` |
| POST | `/control` | `{op\|mode: take\|handback\|watch\|shared\|user}` | same, after the change |
| POST | `/input` | `{type: key\|click\|move, text?, key?, keys?, x?, y?, button?}` | injects user input; starts the shared hold-off |
| POST | `/vm` | `{op: start\|stop\|reset\|...}` | VM lifecycle (same ops as `templeos_vm`) |
| POST | `/start` | `{flavor?, name?}` | alias for `/vm` `op=start` |
| POST | `/stop` | | alias for `/vm` `op=stop` |
| POST | `/reset` | | alias for `/vm` `op=reset` |
| GET | `/snapshots` | | `{ok, snapshots, snapshot}` |
| POST | `/snapshots` | `{op: save\|restore, name?}` | savevm / loadvm (ejects non-qcow2 writables first) |
| GET | `/log` | `?limit=` | recent agent/user actions (`api.note_agent_action`) |
| GET | `/doctor` | | doctor report (QEMU, ISO pin, KVM openable) |
| POST | `/setup` | `{flavor?}` | fetch/verify the pinned ISO, then doctor |

All of these routes are implemented. `/frame` and `/input` return
`vm_not_running` when the guest is stopped (never a slice stub). `/input`
always records the user event so the shared-mode hold-off works, even if
injection fails. `dashboard/plugin_api.py` wraps `templeos.tools.HANDLERS`
so tool calls appear in `GET /log`.

## Pane protocol

1. `registerTempleOSPane(ctx)` stores `ctx.rest` via `setHostTransport`.
2. The pane polls `GET /status` and `GET /frame`.
3. Frame `data` is decoded to a Blob URL and the previous URL is revoked.
4. Take control posts `{op:"take"}`; Hand back posts `{op:"handback"}`.
5. Clicks on the 640×480 (integer-scaled) screen post `POST /input`.
6. In watch mode the pane must not post user input.
7. Show a chip for running / snapshot / kvm|tcg / mode, and an Agent log.
8. Do not default the pane to JPEG. Prefer PNG. 10–15 fps is enough.

## Fakes

`tests/fakes.py` (integration-owned) provides `FakeQMP`, `FakeSerial`, and
`FakeCtx`. Slices should test against these rather than live QEMU whenever
possible.

- `FakeQMP`: records commands, writes a tiny PNG on `screendump`, can
  simulate missing absolute-mouse handler, writable-floppy `savevm` failure,
  and a failed `loadvm` that leaves the VM paused until `cont`.
- `FakeSerial`: bytes written by the guest are dropped unless `open()` was
  already called.
- `FakeCtx`: records `register_tool` / `register_skill`.

## Security

- No dotenv. No `requires_env`. No `os.environ` secret fallback.
- Child env is an exact-name allowlist (`templeos.envsafe.child_env`).
- Paths resolve symlinks and stay under `TEMPLEOS_HOME` / plugin data.
  The data root must not be a filesystem root.
- QMP, VNC, COM1 are unix sockets under the data dir. Never advertise a
  LAN VNC port.
- Catalog rule 17: do not bundle QEMU, the ISO, a preinstalled qcow2, or WASM.
- Desktop: `@hermes/plugin-sdk` / React only; no `eval`, no `new Function`,
  no prototype patching, no session token reads.

## Files protocol (Slice D)

`templeos.files` implements `list_guest`, `pull`, and `push`.

- Primary transport: framed COM1 (`TXFR` magic, additive U32 checksum). See
  `docs/FILES.md` and `skills/templeos-operator/guest/Xfer.HC`.
- Bind a port for tests with `templeos.files.bind_serial(FakeSerial(...))`.
  Production should expose the live port via `templeos.vm.get_serial()` once
  Slice A lands.
- When COM1 is not bound (`bind_serial` / `vm.get_serial()`), the public
  functions return `serial_not_ready`. Mid-transfer failures also use
  `serial_not_ready`. `push` may fall back to experimental FAT only when
  the VM does not appear running.
- Experimental FAT push lives in `_push_via_fat` (stopped VM only). Never
  mount the live RedSea qcow2 while QEMU has it open.
- Caps: 256 KiB file, 200-char guest path, exchange dir under `home()/exchange/`.

## Host and first run (Slice A / doctor)

1. Find `qemu-system-x86_64`, print version, test-open `/dev/kvm`.
2. Fetch the default TinkerOS ISO (or the selected flavor) from the official
   URL, verify SHA-256, store under `home()/isos/`.
3. `qemu-img create -f qcow2` a 2G disk under `home()/disks/`.
4. After a clean HolyC prompt, `savevm golden`. Later starts `loadvm golden`
   and `cont` if paused.
5. On TinkerOS, initialize serial in golden: `CommInit;` then
   `CommInit8n1(1,115200);`.
