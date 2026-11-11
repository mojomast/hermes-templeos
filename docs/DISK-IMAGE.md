# Preinstalled Temple of Hermes disk image (optional)

Temple of Hermes stays the default guest flavor (`templeoh`). The preinstalled
disk image is an **option** for that flavor: when it is enabled and verified,
the guest boots with local storage (`C:`) already present instead of booting
the live ISO with an empty scratch disk. With the option off, or before the
image is published, boot behavior is exactly the existing live-ISO path.

## Pinned artifact

| Field | Value |
| --- | --- |
| File | `TempleOfHermes-0.1.2-disk.qcow2` |
| SHA-256 | `d41672fb148051f3b4d85d06895bfc0f67da0e3af539bf89bbf4933056241087` |
| Size | 11,082,240 bytes |
| Format | Compressed qcow2, 4 GiB virtual size |
| Contents | MBR + FAT32 TinkerOS install of the official v0.1.2 ISO |
| Boot | Reaches the Hermes launcher with no CD; `C:/Home` and `C:/Hermes/Apps/HermesBBS` precreated |

The image is not published yet, so the plugin does not invent or guess a
download URL. The record in `templeos/diskimage.py` pins the filename, SHA-256
and size, and keeps a single clearly-marked constant for the future release
URL. Until that is set, the pane and doctor show **not published**.

## Enable it

1. Download the pinned disk image from its official release when one exists.
2. Verify it yourself against the SHA-256 and size above.
3. Point the plugin at the local file, either through config
   `disk_image_path` or the `TEMPLEOS_DISK_IMAGE` environment variable.
4. Set `disk_image` to `"on"` (config) or use the pane toggle
   **Preinstalled disk (local storage)** under Temple of Hermes.

The pane persists both values through the existing `/settings` route; no tool
schema changes and no new tool are involved.

Example config fragment:

```yaml
disk_image: "on"
disk_image_path: "/path/to/TempleOfHermes-0.1.2-disk.qcow2"
```

`TEMPLEOS_DISK_IMAGE` overrides `disk_image_path` when both are present.

## Verification

Before every use the plugin checks:

- the file exists;
- its size equals exactly 11,082,240 bytes;
- its SHA-256 equals
  `d41672fb148051f3b4d85d06895bfc0f67da0e3af539bf89bbf4933056241087`.

A mismatch is refused with a structured error and the guest falls back to the
normal live ISO plus scratch disk. Doctor reports the image as `missing`,
`unverified`, or `ok` without fetching anything.

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
