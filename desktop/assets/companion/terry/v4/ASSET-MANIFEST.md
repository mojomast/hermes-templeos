# Terry v4 high-res asset bundle

- Display scale: **3.5x** the original 192×208 cell (target figure ~650–700px tall at 1920×1240).
- Slot parts were LANCZOS-downsampled from `modular/out/masters/` to `slot_size * 3.5` and PNG-optimized.
- Smoke textures: 448×448 from the smoke masters (replacing 128×128 package assets).
- Total: **13193850 bytes (12.58 MB)** of 25 MB budget. File count: 68.
- Do not use the old 192×208 atlas with pixelated upscaling. Use `runtime/companion.js` with smooth, DPR-aware scaling and these parts.
- `baked-presets.json` has clips: idle, typing, talking, vm_booting, celebrate_short, greet, failed, waving, smoking, dance, and others.

## Top-level sizes
- `CHANGES.md`: 4108 bytes (0.00 MB)
- `INTEGRATION-V2.md`: 6492 bytes (0.01 MB)
- `INTEGRATION.md`: 12478 bytes (0.01 MB)
- `README.txt`: 5593 bytes (0.01 MB)
- `SCALE.json`: 1145 bytes (0.00 MB)
- `atlas.json`: 7718 bytes (0.01 MB)
- `baked-presets.json`: 10064152 bytes (9.60 MB)
- `parts`: 2410166 bytes (2.30 MB)
- `parts.json`: 17399 bytes (0.02 MB)
- `presets`: 8086 bytes (0.01 MB)
- `rig.json`: 1607 bytes (0.00 MB)
- `runtime`: 5761 bytes (0.01 MB)
- `smoke`: 647485 bytes (0.62 MB)
- `speech.json`: 1660 bytes (0.00 MB)
