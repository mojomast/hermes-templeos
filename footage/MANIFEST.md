# Temple of Hermes 0.1.2 — Desktop pane footage

Submission footage pack for the Hermes Desktop TempleOS pane, using the packed
`hermes-templeos` plugin tree.

- Plugin commit: `0f50faac279f7a669e66a13d0b1ce881a7a86917`
  (`video/footage`, packed from `feat/plugin-integration`)
- Branch used: `video/footage` (local work branch from the packed HEAD)
- Guest: **Temple of Hermes 0.1.2** (TinkerOS 5.20 base), network off
- ISO actually booted:
  - file: `TempleOfHermes-0.1.2.ISO`
  - SHA-256: `d6af7663cbc27a93a08881485ce355652a31e1bace86f50e5005e44e5db3f3e5`
  - size: `14,030,848` bytes
  - ISO9660 volume id: `THE_TEMPLE_OF_HERMES`
- ISO source: no local copy with the reference SHA-256
  (`8bcf43c31689e328716ca42f0255f1ede834dd39cd0fa345bc96719d60f74c60`) was
  present. The ISO was rebuilt on this PC from `mojomast/temple-of-hermes`
  branch `hermes/iso-0.1.2` at commit
  `190501f12f13244e5d4cbd259d2cffaac1d74e03`, following
  `docs/ISO-BUILD.md` / `scripts/build_iso.py` (TinkerOS install to qcow2,
  FAT32 overlay, in-guest `MakeDistro`/`RedSeaISO`, host extraction). The
  rebuilt image has the documented size and volume id; its hash differs from
  the reference build, so the rebuilt hash above is the one actually booted.
  The ISO is not in the git tree.

## Capture

- Real X11 screen capture at 1920x1080, 30 fps, H.264 MP4 (`libx264`, CRF 20,
  `yuv420p`, faststart), 6–15 s per clip, all under 50 MB.
- The packed pane (`desktop/src/ui`) was rendered at 1920x1080; its `ctx.rest`
  calls were served by the packed `templeos.api` / `templeos.tools` /
  `templeos.vm` modules. QEMU is the plugin's own child, with the ISO above.
  No plugin code, tool schema, or plugin file was changed for this pack.
- Guest frames are the pane's live frame feed (PNG frames polled by the pane),
  not a slideshow of stills.

## Clips

| File | What is shown | Duration | Resolution | FPS | Size |
| --- | --- | ---: | --- | ---: | ---: |
| `01-boot.mp4` | Pane stopped, Power/Start pressed, QEMU boot splash, then the 18-entry Temple of Hermes launcher. | 14.5 s | 1920x1080 | 30 | 805,888 B (0.81 MB) |
| `02-pane-overview.mp4` | Full pane at the launcher: live VM screen on the left, HD Terry on the right, agent log below the screen with recent tool events. | 10.0 s | 1920x1080 | 30 | 653,725 B (0.65 MB) |
| `03-agent-drives.mp4` | Agent uses `templeos_screen` and `templeos_input` (click on the WorldSim launcher icon, then keys to return); agent log updates and Terry shows the typing state while tools are in flight. | 13.0 s | 1920x1080 | 30 | 1,480,368 B (1.48 MB) |
| `04-holyc.mp4` | Agent opens a guest HolyC shell and uses `templeos_input op=holyc` to write and run `I64 x=6*7; "HolyC from Hermes: x=%d\n",x;`; output `x=42` appears. | 12.0 s | 1920x1080 | 30 | 944,775 B (0.94 MB) |
| `05-take-control.mp4` | User clicks **Take control**; an agent tool call then returns `agent_paused`; the user types `5+6;` into the pane keyboard and the guest returns `ans=0x0000000B=11`. | 11.0 s | 1920x1080 | 30 | 919,118 B (0.92 MB) |
| `06-launcher.mp4` | The 18-entry launcher grid with a slow guest-cursor pan across the icon rows. | 10.0 s | 1920x1080 | 30 | 944,337 B (0.94 MB) |
| `07-apps-montage.mp4` | Hermes Chat, WorldSim, Psyche, Dojo, Southpaw, BBS, and Caduceus, each opened from the launcher and shown for a short segment. | 14.5 s | 1920x1080 | 30 | 1,468,958 B (1.47 MB) |
| `08-bbs.mp4` | Guest HBBS/1 client against a **LOCAL** hbbs instance: list boards, read the General thread (post by test account **Test Pilgrim** and agent reply by **Hermes Agent**), then a live post by the test account. | 15.0 s | 1920x1080 | 30 | 1,697,871 B (1.70 MB) |

All eight files are H.264 MP4, 1920x1080, 30 fps, and between 10 and 15
seconds.

## Caveats

- **07 montage pacing.** The global 6–15 s limit conflicts with 3–5 s per app
  for seven apps. The montage uses roughly 1.4 s per app so the clip stays at
  14.5 s. All seven requested apps opened; none were skipped.
- **07 BBS segment.** The BBS app is shown opening while no guest token was
  loaded, so it displays its OFFLINE fallback board list. The full local BBS
  list/read/post session is in `08-bbs.mp4`.
- **08 is LOCAL.** A local hbbs instance on loopback was used (no public BBS,
  no tailnet, no VPS). Test accounts are `Test Pilgrim` (human) and
  `Hermes Agent` (agent, owned by Test Pilgrim). The read output contains the
  seeded test post and agent reply; the final operation posts a new General
  thread as the test account. No endpoint, hostname, IP, or token is shown on
  screen or recorded here.
- **04 shell setup.** The HolyC shell window was opened through the guest HRPC
  console off-camera; the on-camera writing/running is the plugin's
  `templeos_input op=holyc` tool.
- **05 user input.** Take control is a real pane-button click; the user's
  `5+6;` is real keyboard input through the pane, not an agent tool call.
- **06 cursor.** The pan is the guest cursor moved with `templeos_input
  op=move` across the icon rows; no icons are activated.
- **No blur/crop needed.** No tokens, env files, secrets, hostnames, IPs, or
  private URLs appear in these clips. The only network name shown is the
  guest's allow-list destination literal `bbs` and the LOCAL label.
- **ISO hash.** The rebuilt ISO hash differs from the reference hash because
  the in-guest ISO writer is not bit-for-bit deterministic; size and volume id
  match the documented artifact. The hash above is the image that was booted.
