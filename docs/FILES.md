# Host ↔ guest file transfer

Primary path: framed COM1 protocol + HolyC helper
`skills/templeos-operator/guest/Xfer.HC`.

## Frame layout (little-endian)

| Field | Size | Notes |
|---|---|---|
| magic | 4 | ASCII `TXFR` |
| cmd | 1 | see below |
| len | 4 | payload length |
| payload | len | |
| sum | 4 | `cmd + Σ payload bytes` (U32 wrap) |

### Commands

| cmd | Direction | Payload |
|---|---|---|
| `0x01` LIST | host → guest | guest path UTF-8 (e.g. `T:/Home/`) |
| `0x02` PULL | host → guest | guest file path UTF-8 |
| `0x03` PUSH | host → guest | `path UTF-8` + `NUL` + file bytes |
| `0x81` LIST_OK | guest → host | JSON array `[{"name","is_dir"}, …]` |
| `0x82` PULL_OK | guest → host | raw file bytes |
| `0x83` PUSH_OK | guest → host | empty |
| `0x8F` ERR | guest → host | UTF-8 message |

Limits: path ≤ 200 chars, file ≤ 256 KiB, list ≤ 512 entries.
Guest paths must match `T:/…` style with no `..`.

## Setup on TinkerOS

1. Host keeps COM1 open for the whole session (`templeos_vm op=start`).
2. Guest: `CommInit;` then `CommInit8n1(1,115200);`.
3. Install helper (push or `holyc`), then `XferServe;` (or `XferServeOnce;` in a loop).

## Experimental FAT push

When COM1 is down and the VM does **not** appear running, `push` may build
`exchange/xfer.img` (FAT) under the plugin data dir with `mkfs.vfat` /
`mtools`. The bake-off found a hot-added FAT12 floppy was **not** visible as
`A:` on the TinkerOS live CD, so this path is marked `experimental: true` and
must never mount the live RedSea qcow2 while QEMU has it open.

## Testing

Unit tests drive `tests.fakes.FakeSerial` through `templeos.files.bind_serial`
with a cooperative guest loopback (`tests/test_files.py`). No live QEMU
required.
