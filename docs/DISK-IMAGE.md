# Preinstalled Temple of Hermes disk image (on by default)

Temple of Hermes stays the default guest flavor (`templeoh`). The preinstalled
disk image is an option for that flavor, **on by default**: the guest boots
with local storage (`C:`) already present instead of the live ISO with an
empty scratch disk. If the download or verification fails, or the option is
off, boot behavior is exactly the existing live-ISO path.

## Pinned artifact

| Field | Value |
| --- | --- |
| File | `TempleOfHermes-0.1.3-disk.qcow2` |
| URL | <https://github.com/mojomast/temple-of-hermes/releases/download/v0.1.3/TempleOfHermes-0.1.3-disk.qcow2> |
| Release | [v0.1.3](https://github.com/mojomast/temple-of-hermes/releases/tag/v0.1.3) |
| SHA-256 | `d81a3c189093bd0edddad50b7a55d6582d0490204d63720e14fc5fb9d901f1aa` |
| Size | 11,107,840 bytes |
| Format | Compressed qcow2, 4 GiB virtual size |
| Contents | MBR + FAT32 TinkerOS install of the official v0.1.3 ISO |
| Boot | Reaches the Hermes launcher with no CD; `C:/Home` and `C:/Hermes/Apps/HermesBBS` precreated |

The record lives in `templeos/diskimage.py` (`DISK_IMAGE_URL`, `DISK_SHA256`,
`DISK_BYTES`).

## How it is fetched

- `templeos_vm op=doctor` with setup, or the first `start` with the option on,
  downloads the asset once into the plugin data dir (`disks/`).
- The download uses the same path as the pinned ISOs: public HTTPS only,
  connection-pinned, no ambient proxy, size-capped, and the SHA-256 must match
  or the partial file is deleted.
- Any failure (offline, TLS, size or hash mismatch) is a status, not a boot
  error: the guest boots the live ISO and the pane shows
  **download failed, using live ISO**.

## Turn it off or use your own copy

- Pane: uncheck **Preinstalled disk (local storage)** under Temple of Hermes.
- Config: `disk_image: "off"`.
- Use a local copy instead of downloading: set `disk_image_path` (or
  `TEMPLEOS_DISK_IMAGE`, which wins). It is verified the same way.

```yaml
disk_image: "on"            # default
disk_image_path: ""         # optional local copy
```

The pane persists both values through the existing `/settings` route; no tool
schema changes and no new tool are involved.

## Verification

Before every use the plugin checks:

- the file exists;
- its size equals exactly 11,107,840 bytes;
- its SHA-256 equals
  `d81a3c189093bd0edddad50b7a55d6582d0490204d63720e14fc5fb9d901f1aa`.

A mismatch is refused with a structured error and the guest falls back to the
normal live ISO plus scratch disk. Doctor reports the image as `not_downloaded`, `download_failed`, `missing`,
`unverified`, or `ok`; plain doctor checks never download, only setup does.

## Overlay and persistence

The pinned base is never modified. When the option is on and the image
verifies, the plugin creates a per-user copy-on-write qcow2 overlay under the
plugin data directory:

```
qemu-img create -f qcow2 -b <base> -F qcow2 <overlay>
```

QEMU boots the overlay as the hard disk with no CD. Changes made inside the
guest (including `C:`) persist in the overlay across restarts. Deleting the
overlay resets the guest to the pinned base image; the base file is untouched.

## Notes

- Only `templeoh` uses the disk option. TinkerOS, stock TempleOS and ZealOS are
  unchanged.
- Networking remains off (`-nic none`).
- No QEMU binary, ISO or disk image is bundled with the plugin.
