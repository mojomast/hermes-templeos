---
name: templeos-operator
description: >-
  Skill id templeos:templeos-operator. Load it with
  skill_view("templeos:templeos-operator"). Drive a local TempleOS-family
  QEMU guest (default TinkerOS 5.20-rc10) with the four templeos_* tools,
  then look or read_text. Open the TempleOS Desktop pane so the user can
  watch and Take control or Hand back. Networking is always off.
version: "0.1.0"
author: mojomast
license: MIT
compatibility: >-
  Python 3.10+, Hermes >= 0.23.0, qemu-system-x86_64 and qemu-img on PATH.
  Linux x86_64 is the primary host. KVM is used only when /dev/kvm can be
  opened; otherwise TCG. No secrets. The plugin does not open a dotenv file.
metadata:
  hermes:
    tags: [templeos, qemu, desktop]
    category: tools
    related_skills: []
---

# TempleOS operator

This skill is a stub. Slice D will expand it once the VM, screen, input and
files slices land. Until then, follow the contracts in `docs/CONTRACTS.md`.

## Tools

- `templeos_vm` — `start` `stop` `reset` `snapshot` `restore` `status` `doctor`
- `templeos_screen` — `look` `read_text` `wait_idle` `hash`
- `templeos_input` — `type` `keys` `click` `move` `holyc`
- `templeos_files` — `list` `pull` `push`

Every tool returns a JSON string `{ok, error, code, fix, ...}`.

## Flow (once implemented)

1. `templeos_vm` `op=doctor` if the host or ISO may be missing.
2. `templeos_vm` `op=start` (default flavor `tinkeros`).
3. `templeos_screen` `op=wait_idle`, then `read_text` or `look`.
4. `templeos_input` to type or click. If you get `agent_paused`, tell the user
   the pane is in Take control or the shared-mode hold-off, and wait or ask
   them to click Hand back.
5. After a consequential `holyc` or `type`, `wait_idle` then `read_text` or
   `look` once. Do not flood the context with frames. Default 640x480 looks
   cost about 414 visual tokens; ZealOS 1024x768 is about 1036 — do not switch
   flavors casually.

## Recovery

If a tool returns `not_implemented`, say the matching slice has not landed
yet. If `qemu_missing` or `iso_missing`, run doctor and show the fix. If the
pane is blank, the user should enable the plugin and Rescan; the pane talks
only through `ctx.rest`.

## Safety

The plugin spawns a child hypervisor with networking off. Do not ask to enable
a NIC. Host paths for `templeos_files` must stay under the plugin data dir.
