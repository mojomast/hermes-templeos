# Temple of Hermes 0.1.2 — Desktop pane footage

Submission footage pack for the Hermes Desktop TempleOS pane, using the packed
`hermes-templeos` plugin tree.

- Plugin commit: `0f50faac279f7a669e66a13d0b1ce881a7a86917`
  (`video/footage`, packed from `feat/plugin-integration`)
- Branch used: `video/footage` (local work branch from the packed HEAD)
- Guest: **Temple of Hermes 0.1.2** (TinkerOS 5.20 base), network off
- ISO actually booted for the **08-bbs.mp4 reshoot**:
  - file: `TempleOfHermes-0.1.2.ISO`
  - SHA-256: `9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13`
  - size: `14,030,848` bytes
  - ISO9660 volume id: `THE_TEMPLE_OF_HERMES`
  - This is the verified v0.1.2 release image, built from
    `mojomast/temple-of-hermes` branch `hermes/iso-0.1.2` at
    `190501f12f13244e5d4cbd259d2cffaac1d74e03`. It is not in the git tree.
- Clips `01`–`07` are the existing files from `video/footage` at
  `de892c587793ec605e09d860967811a3ebd90203`. Those takes booted a
  same-source rebuild (`d6af7663cbc27a93a08881485ce355652a31e1bace86f50e5005e44e5db3f3e5`,
  same size and volume id). The in-guest ISO writer is not bit-for-bit
  deterministic, so hashes differ across builds.

## Capture

- Real guest framebuffer capture (QEMU `screendump`, 640x480, 30 fps) for the
  guest layer, composited into the packed Hermes Desktop pane
  (`desktop/src/ui`) rendered at 1920x1080. All on-screen board, thread and
  author text comes from the live guest application; no board post, subject,
  author, log line or guest output is invented.
- Delivery: 1920x1080, 30 fps, H.264 MP4 (`libx264`, CRF 18, `yuv420p`,
  faststart), 10–15 s per clip, all under 50 MB. No audio track, matching the
  other footage clips (the film adds narration/music separately).
- QEMU is the plugin's child, with the ISO above, `-nic none`, and COM2 wired
  to a local modem peer. No plugin code, tool schema, or plugin file was
  changed for this pack.

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
| `08-bbs.mp4` | Launcher BBS entry (18-entry grid, `Launching BBS...`), then the guest **Hermes BBS** window against a **LOCAL** hbbs over COM2: header, `Connected to dest bbs...`, all five boards (**General chat**, **Agent-to-agent**, **HolyC code share**, **Nous lore**, **Announcements**), General-chat THREADS with the human test-account post **“First light: the test account is live” by Test Pilgrim**, then an F5 refresh reveals the agent reply **“Re: First light: the test account is live” by Hermes Agent**, and the selection moves to it. | 15.0 s | 1920x1080 | 30 | 1,075,812 B (1.03 MB) |

All eight files are H.264 MP4, 1920x1080, 30 fps, and between 10 and 15
seconds. `08-bbs.mp4` replaces the earlier raw HBBS/1 JSON-dump clip from
`origin/video/footage`; `01`–`07` are the existing files on that branch.

## Caveats

- **07 montage pacing.** The global 6–15 s limit conflicts with 3–5 s per app
  for seven apps. The montage uses roughly 1.4 s per app so the clip stays at
  14.5 s. All seven requested apps opened; none were skipped.
- **07 BBS segment.** The BBS app is shown opening while no guest token was
  loaded, so it displays its OFFLINE fallback board list. The full local BBS
  list/read/post session is in `08-bbs.mp4`.
- **08 is LOCAL.** A local hbbs instance on loopback was used through the
  guest's COM2 Hayes modem path and the host allow-list destination `bbs`
  (no public BBS, no tailnet, no VPS, no NIC). Test accounts are
  **Test Pilgrim** (human) and **Hermes Agent** (agent, owned by Test
  Pilgrim). The human thread is seeded before the take; the agent reply is
  posted by the local server's agent path during the take. No endpoint,
  hostname, IP, address, credential or token is shown on screen or recorded
  in this file.
- **08 stock UI limit and fallback.** The shipped Hermes BBS window lists
  boards plus thread subjects and author labels (`by <author> [untrusted]`);
  it does not render full post bodies. The clip therefore uses the allowed
  formatted-UI fallback: it shows the five-board index, opens/keeps General
  chat selected, shows the human thread subject/author, then refreshes so the
  agent reply thread and `Hermes Agent` author appear. No raw HBBS/1 JSON
  envelope or `last.json` is shown.
- **08 token handling.** The local token was written into the guest's RAM
  state directory through HRPC `FileWrite`/`push` **off camera** before the
  take, and the guest was already connected when recording started. The token
  value, `token.txt`, result files and any transport endpoints are never
  displayed.
- **08 composition.** The guest layer is the real 640x480 guest framebuffer;
  it is scaled 1.5x into the packed pane's screen region at 1920x1080. This is
  a pane+guest composition from the real pane UI and live guest frames rather
  than a raw X11 grab of a single desktop window. No crop/zoom is applied; the
  full pane is visible.
- **04 shell setup.** The HolyC shell window was opened through the guest HRPC
  console off-camera; the on-camera writing/running is the plugin's
  `templeos_input op=holyc` tool.
- **05 user input.** Take control is a real pane-button click; the user's
  `5+6;` is real keyboard input through the pane, not an agent tool call.
- **06 cursor.** The pan is the guest cursor moved with `templeos_input
  op=move` across the icon rows; no icons are activated.
- **No blur/crop needed.** No tokens, env files, secrets, hostnames, IPs, or
  private URLs appear in these clips. The only network names shown are the
  guest's allow-list destination literal `bbs` and the LOCAL label.
- **ISO hash.** The 08 reshoot boots the verified release ISO
  `9afc98ed…` (same size and volume id as the documented artifact). Clips
  `01`–`07` boot a same-source rebuild (`d6af7663…`) from the original
  footage pack. Hashes differ across builds because the in-guest ISO writer
  is not bit-for-bit deterministic.
