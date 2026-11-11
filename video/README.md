# ONE LIVE SCREEN — 90-second submission edit

**Hyperrizz / HyperFrames**, with a complete 1920×1080 / 30fps edit and a separately laid-out 1080×1920 / 30fps composition. Both are exactly **90 seconds / 2,700 frames**. The delivered preview includes the six supplied HD Terry loops and verbatim sourced quotes; all eight live-screen recordings remain clearly labelled footage placeholders. It is a production handoff, not a live feature demonstration.

## Quick start

Requirements: Node.js 22+, Python 3, FFmpeg + ffprobe (with `libx264`, `libvpx-vp9` and `loudnorm`), and Chromium. HyperFrames can provision its browser. The voice/music/fonts are already bundled; no model, API key, QEMU or running Hermes instance is needed to render this edit.

From the repository root:

```bash
cd video
npm ci
npm run build
npm run preview
```

`npm run preview` opens the HyperFrames studio. Build first after replacing source media: the build regenerates a content-addressed decoded-frame cache and never overwrites files in `footage/` or `assets/terry/`.

### Render

```bash
cd video
npm run render
```

Outputs:
- `out/submission.mp4` — 1920×1080 / 30fps H.264/AAC master.
- `preview/submission-placeholder.mp4` — 1280×720 / 30fps compact preview, committed in this branch.
- `preview/submission-placeholder-1080p.mp4` — committed copy of the verified 1080p master.

The renderer uses two HyperFrames workers, low priority and two-core affinity on Linux. Decoder/encoder/filter concurrency is capped. Audio is explicitly muxed, then the files undergo full decode, frame/duration/loudness/size verification before atomic rename. Each delivery file must remain below **49,000,000 bytes**, leaving margin under the requested 50 MB limit.

After all eight real captures are supplied:

```bash
npm run render -- --final
```

`--final` rejects incomplete inputs instead of delivering a final-labelled film with missing assets. Its preview is named `preview/submission-final.mp4`; it retains the existing placeholder preview. The default renderer always fails gracefully to clearly labelled placeholders.

### Vertical composition

```bash
node scripts/build.mjs --vertical
npx hyperframes preview .build
# Full 1080×1920 render, plus 720×1280 compact preview:
npm run render:vertical
```

The vertical version stacks the original 4:3/whole-pane image, host, callouts and captions; it does not crop the landscape MP4. Run `npm run build` to return the studio to landscape. `CHROME_BIN` can point QA scripts at an existing headless Chromium; `PRODUCER_HEADLESS_SHELL_PATH` selects an existing browser for HyperFrames.

Both vertical exports are also committed: `preview/submission-placeholder-vertical-1080p.mp4` (1080×1920) and `preview/submission-placeholder-vertical.mp4` (720×1280). All four files, checksums and measured audio results are recorded in `preview/verification.json`.

## Footage slot table

Drop the exact filenames into **`video/footage/`**. Source audio is muted; narration/music are authored separately. Each clip must cover its full duration after `sourceIn` (seconds, default 0, editable in `slots.json`). Missing, corrupt, too-short or unsupported inputs keep the README still, `PLACEHOLDER` and `FOOTAGE: <filename>` labels. Labels disappear only when a usable real clip is decoded.

| Timeline | Duration | Exact path | Capture contents | Temporary README still |
|---|---:|---|---|---|
| 00:00–00:08 | 8s | `footage/01-boot.mp4` | Actual custom-guest boot splash → usable launcher | OS `boot-splash.png` |
| 00:08–00:20 | 12s | `footage/02-pane-overview.mp4` | Complete Hermes pane, shared screen, Terry at right, real agent log below | Plugin `pane-1920x1240.png` |
| 00:20–00:28 | 8s | `footage/03-agent-drives.mp4` | Agent clicks launcher, types, opens files; log visibly updates | Plugin `pane-1920x1240.png` |
| 00:28–00:37 | 9s | `footage/04-holyc.mp4` | Write/run HolyC, inspect real output and open the file | OS `shell.png` |
| 00:37–00:45 | 8s | `footage/05-take-control.mp4` | User clicks Take control; agent pauses; user drives; Hand back | Plugin `pane-user-driving.png` |
| 00:45–00:51 | 6s | `footage/06-launcher.mp4` | Full 18-entry 6×3 launcher, entry and return | OS `home-launcher.png` |
| 00:51–01:05 | 14s | `footage/07-apps-montage.mp4` | 0–3s WorldSim; 3–6s Capybara/Dojo; 6–9s Messenger/Caduceus; 9–14s Codex/Offerings lore and art | OS `home-launcher.png` |
| 01:05–01:20 | 15s | `footage/08-bbs.mp4` | HBBS/1 board list, then a real human and agent posting to General chat | OS `bbs.png` |

Guest-only capture may remain 640×480; whole-pane footage should be at least 1440×1000 for legible controls/logs. Prefer 30fps or higher. Preserve aspect ratio and important context. No fake cursor movement, invented log lines, simulated HolyC output or fictional BBS posts are added by the edit. **Never capture credentials, tokens, keys, environment files, private hostnames, tailnet addresses or IPs.**

The source `pane-1920x1240.png` shows the updated pane with Terry on the right and the log below, but the guest is still TinkerOS. The Take control stand-in comes from the earlier README layout. Neither is rebuilt or relabelled as the custom guest. Replacements must show the requested real layout and guest. Slots fit the whole source; adjust composition sizing in `scenes/` if the capture has excessive empty chrome.

## Terry animation and verbatim quote handoff

The initial plugin revision `e16c9e7` lacked the requested assets, and the user approved labelled missing-asset slots. During production, `feat/plugin-integration` advanced to **`0f50faac279f7a669e66a13d0b1ce881a7a86917`**, supplying all six loops and the quote catalogue. This submission branch is based on that updated commit and includes the exact original assets. Their declared hashes match. The earlier static HD v4 stand-in remains a visibly labelled fallback only if a loop is removed or fails validation.

Bundled source loops:

```text
video/assets/terry/idle.webm
video/assets/terry/walk.webm
video/assets/terry/speaking.webm
video/assets/terry/wave.webm
video/assets/terry/typing.webm
video/assets/terry/smoking.webm
```

Format: **transparent VP9, 720×1080, 20fps**, no voice. FFmpeg explicitly uses `libvpx-vp9` to preserve alpha; loops are sampled against absolute scene time. `smoking` is bundled but is not used in this cut. `terry-slots.json` controls filenames and quote cues. Source loops and the exact quote catalogue are committed under `assets/terry/`.

**`video/assets/terry/approved-quotes.json`** is a byte-for-byte copy of `desktop/terry-quotes.json`. Upstream is an array without `id` fields, so cue IDs use its **zero-based JSON Pointers** (`#/19`, `#/6`), pinned to the commit and catalogue SHA-256. These are source locations, not invented quote identifiers or added catalogue fields. The renderer resolves **only exact original text**. Catalogues with explicit string IDs are also supported. Both selected lines are short and non-hateful; no paraphrasing or voice impersonation is used.

| Quote slot | On screen | Current quote ID | Status |
|---|---|---|---|
| `opening-quote` | 00:05.5–00:08 | `#/19` | “Yes, I wrote the compiler from scratch.” — TempleOS FAQ |
| `closing-quote` | 01:20–01:23.5 | `#/6` | “Users should see the light at the end of the tunnel.” — TempleOS Charter |

The unchanged pane screenshot also contains catalogue entry **`#/32`** (the Commodore 64 / open-source quotation) during 00:08–00:28. It is part of the labelled README evidence, not an additional animated bubble. **No synthesized or cloned Terry voice is used.** The speaking loop is a silent text-bubble performance; the female narrator is separate.

## Shot list

| Time | Shot | Motion / host | Quote ID |
|---|---|---|---|
| 00:00–00:08 | CRT power-on, THE TEMPLE OF HERMES | Signal expansion, grid depth, walk → wave | `#/19` at 00:05.5 |
| 00:08–00:20 | Your agent and you. One live TempleOS screen. | Screen push, cyan/yellow shared rail, idle | `#/32` in README still |
| 00:20–00:28 | See. Click. Type. | Beat drop, glitch cut, action labels, typing | `#/32` in README still |
| 00:28–00:37 | Write HolyC. Run it. Open it. | Large type / source screen, typing | — |
| 00:37–00:45 | Take control. The agent pauses. | Yellow handover rail, idle | — |
| 00:45–00:51 | 18 entries. One launcher. | Macro numeral → full grid, wave | — |
| 00:51–01:05 | Apps, lore and art | Four timed callouts, gentle screen push, wave → idle | — |
| 01:05–01:20 | Human + agent. Same board. | Five-board index beside real BBS slot | — |
| 01:20–01:25 | Install + both repositories | Speaking loop and approved quote bubble | `#/6` at 01:20 |
| 01:25–01:30 | Memorial | Static five-second end hold; music resolves | — |

Exact end card:

> Terry A. Davis (1969–2018), creator of TempleOS. Fan tribute; not affiliated with Terry's estate, TinkerOS, or Nous Research.

## Source and claim ledger

- Plugin branch: [`feat/plugin-integration`, 0f50faa](https://github.com/mojomast/hermes-templeos/tree/0f50faac279f7a669e66a13d0b1ce881a7a86917). Read README, `templeos/tools.py`, `templeos/flavors.py`, Desktop assets and README screenshots. Earlier stand-ins retain their original `e16c9e7` provenance.
- OS branch: [`hermes/readme`, 44d4c54](https://github.com/mojomast/temple-of-hermes/tree/44d4c542d64b40513a635494ac791d281b748fc4). Read README, `docs/USING-WITH-HERMES-AGENTS.md`, and `shots/hermes-iso-0.1.2/VERIFY.md` / shot inventory.
- Lineage: Terry's TempleOS → TinkerOS → THE TEMPLE OF HERMES; the OS is public domain / Unlicense. The plugin is MIT.
- Shared input and Take control/Hand back are in the plugin README. Four tools remain `templeos_vm`, `templeos_screen`, `templeos_input`, `templeos_files`.
- The 18 registry entries are Temple, Hermes Chat, WorldSim, Codex, Psyche, Capybara, Messenger, BBS, Threshold, Dojo, Offerings, Southpaw, Modem / Net, Caduceus, Token Rain, Spoon, Dojo Duel and About. Temple stays home; About opens help. We say **18 entries**, not 18 games.
- BBS boards: **General chat, Agent-to-agent, HolyC code share, Nous lore, Announcements**. Announcements is read-only for non-sysops. HBBS/1 uses COM2 and an opt-in allow-listed host relay; QEMU needs no NIC. COM1 is distinct from COM2.
- Nous figures are called **characters from the Nous universe**. The edit does not call them game characters or official mascots.

### Integration discrepancy to resolve during capture

The updated plugin README documents the optional BBS bridge and custom guest, while the flavor table still defaults to TinkerOS and lists only TinkerOS/TempleOS/ZealOS; it does not automatically install or select THE TEMPLE OF HERMES. `-nic none` remains correct: COM2 networking is serial, not a guest NIC. The custom OS README describes its guest daemon and host relay. The final capture agent must establish that integration in a real run. This edit does not modify the plugin, run QEMU, claim a verified custom-guest boot, or claim live BBS posting. The on-screen install command is explicitly the **plugin install**, with QEMU/custom image separate.

## Sound, captions and licenses

- Original **120 BPM** score in D minor (Dm–Bb–F–C), seed `1`, downbeat 0, drop **20.000s / frame 600**. Written and rendered in MorningDAW 1.6.3 with Surge XT, Dragonfly Hall/Room and Airwindows ToTape6. Factory drum sounds stay in the MorningDAW install and are not bundled. The project and spec are in `assets/audio/morningdaw/`. Licenses and credits are in `assets/audio/LICENSE.txt`.
- Typing/power/glitch SFX remain the original Python synthesis, **CC0-1.0**.
- Modern female narrator: stock Kokoro-82M v1.0 **fp32** ONNX, a 60/40 blend of **af_heart** and **af_bella** at speed 1.0, original script, no Terry impersonation. Pronunciation for TempleOS, HolyC, WorldSim, HBBS/1, COM2, QEMU and Nous is handled in the spoken text; captions keep the correct spellings. Generated WAVs are bundled; model weights are not. Kokoro-82M weights: Apache 2.0; kokoro-onnx wrapper: MIT.
- `narration.json` holds the script; `assets/narration-timing.json` holds measured cues. Every narration cue is burned in and appears in `captions/narration.srt` with matching times/text. Terry quote bubbles are separate, unspeaking assets.
- `assets/audio/score.wav`, `sfx.wav`, individual `voice/*.wav` and finished `mix.wav` are included. Each WAV is below 50 MB. The finished mix is **-15.0 LUFS / −1.5 dBTP**; the music bed sits at **-22.0 LUFS** and is ducked under the voice. `scripts/music.py` rebuilds the MorningDAW score (when given a local `mdaw` install) and remakes the mix with FFmpeg. Optional `scripts/voice.py --model-dir <kokoro-directory>` requires kokoro-onnx, ONNX Runtime and NumPy, and uses the full-precision `kokoro-v1.0.onnx`. Rendering uses the bundled audio and needs none of these model packages.
- Space Grotesk, IBM Plex Sans and IBM Plex Mono: SIL Open Font License 1.1; original licenses in `assets/fonts/`.
- Terry animation: exact fan-tribute v5 VP9 loops from the updated integration branch, repository MIT; source notes and hashes in `assets/terry/v5-README.md` and `v5-clips.json`. The optional static fallback uses existing v4 artwork, with HD parts/notes in `assets/terry/source/`. `scripts/import-terry.py` and `scripts/import-assets.py` document both imports. No reference photograph or Terry voice recording is included.
- OS README screenshots: Unlicense/public domain. Plugin README screenshots: repository MIT with original public-domain guest pixels. `assets/provenance.json` records original paths, commit URLs, SHA-256 and transformations.

## Verification and editing

```bash
npm run build
npm run lint
npm run check
npm run stills
npm run qa
node scripts/test-slots.mjs
npm run audit
```

`qa` compares reverse and shuffled exact-frame pixels, cut boundaries, motion and effect sensitivity, and checks canvas text bounds. `test-slots` uses an isolated 64×48 color codec fixture to test fallback/decoding; it never writes fake product footage into `footage/`. `audit` checks branch, video-only scope, per-file size, common credential/private-address signatures, exact slots and memorial copy. Review actual captured content before final submission; an automatic signature scan cannot inspect every visual detail.

One source module per shot is in `scenes/`; shared media/typography/runtime are in `shared/`. Copy, palette, slots and timing are JSON. `.build/`, `.cache/`, dependencies and high-resolution intermediate renders are generated/ignored. `scripts/import-assets.py` is a one-time import utility, never part of build. Final measured results and limitations are in `REVIEW.md`.

Source delivery is the `video/submission` branch. A private Tailscale review server was subsequently requested and started; its address is kept out of committed files.
