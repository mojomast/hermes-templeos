# TempleOS (Hermes plugin)

A local QEMU guest the Hermes agent and the user can share. Default flavor is
TinkerOS 5.20-rc10; stock TempleOS 5.03 and ZealOS are optional. Networking is
always off.

This is the Slice 0 scaffold: contracts, tool schemas, a Desktop pane stub, and
leases for the implementation slices. See [docs/CONTRACTS.md](docs/CONTRACTS.md).

**Skill id:** `templeos:templeos-operator`

## Disclosure

The plugin spawns `qemu-system-x86_64` as a child process (KVM only when
`/dev/kvm` can actually be opened; otherwise TCG). It may fetch a pinned ISO
from an official URL and verify SHA-256. It injects keys and HolyC over QMP
and a COM1 unix socket, keeps a background QEMU process, and stores disk
images under the plugin data dir (`TEMPLEOS_HOME` overrides). This is a child
hypervisor, not an OS sandbox. QEMU and ISOs are not bundled.

## Requirements

- Hermes `>= 0.23.0`
- `qemu-system-x86_64` and `qemu-img` on PATH
- Linux x86_64 is the primary host. Apple Silicon and Windows are untested.

## Tools

| Tool | Ops |
|---|---|
| `templeos_vm` | `start` `stop` `reset` `snapshot` `restore` `status` `doctor` |
| `templeos_screen` | `look` `read_text` `wait_idle` `hash` |
| `templeos_input` | `type` `keys` `click` `move` `holyc` |
| `templeos_files` | `list` `pull` `push` |

Every handler returns a JSON string `{ok, error, code, fix, ...}`.

## Install (when a release exists)

```text
hermes plugins install mojomast/hermes-templeos
hermes plugins doctor templeos
```

There is no catalog pin yet. Do not treat the draft in `docs/catalog/templeos.yaml`
as a submitted entry.

## Develop

```bash
python3 -m pytest -q tests
node --import ./tests/js/register-mocks.mjs --test tests/js/*.test.mjs
node scripts/build_desktop.mjs --check
python3 evals/measure_schemas.py
```

Schema budget: keep the four tools under about 2,000 o200k tokens.
