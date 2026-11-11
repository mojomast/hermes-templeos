# Production review — ONE LIVE SCREEN

Status: landscape and portrait placeholder edits rendered, verified and ready for capture handoff.

## Scope and source

90 seconds / 30fps / 2,700 frames. Landscape 1920×1080 and portrait 1080×1920. Hyperrizz / HyperFrames **0.9.33**, checked 2026-11-11 and exactly pinned with a lockfile.

Plugin source: `feat/plugin-integration` at **`0f50faac279f7a669e66a13d0b1ce881a7a86917`**. OS source: `hermes/readme` at `44d4c542d64b40513a635494ac791d281b748fc4`. Initial missing Terry assets were supplied by the updated integration branch during production. All six original transparent VP9 loops are now bundled, with hashes matching the supplied manifest.

All eight README screenshot stand-ins are labelled PLACEHOLDER plus the required footage filename. No rebuilt UI, simulated cursor action, invented log line or fictional BBS post is added. No live OS interaction was performed.

The quote catalogue is a byte-identical copy of `desktop/terry-quotes.json`. It has no explicit IDs; the edit references pinned zero-based JSON Pointers: `#/19` at 5.5–8s, `#/6` at 80–83.5s. The unchanged pane screenshot contains `#/32`. Exact text and source references are in README. No Terry voice is synthesized or cloned.

## Visual/source review

Opening, dense BBS, CTA and memorial reviewed at full resolution; scene contact sheets inspected. Caption bands clear the evidence labels. Portrait host/quote positions are separated. Landscape bubbles sit above the full-height companion. Six HD loop first frames inspected; all 380 decoded source frames have nonempty alpha in the head region. Original fonts, licenses and fan-art source notes are retained.

## Preflight

- Rebuilt both layouts. Lint and strict HyperFrames runtime/layout/craft/audio checks passed with zero errors/warnings.
- Landscape: 40 reverse + 40 shuffled exact-pixel matches; **1,045 canvas text-bound checks**, no violations.
- Portrait: 40 reverse + 40 shuffled exact-pixel matches; **1,082 canvas text-bound checks**, no violations.
- Motion and effect controls change pixels; scene boundaries sampled. Framework DOM analysis is not canvas-text certification: custom bounds and actual still review are used separately.
- Missing/corrupt/short/wrong-alpha media falls back to labelled stills; valid source frames decode. Final mode rejects incomplete footage. Codec fixtures remain outside the footage slots.
- MorningDAW 120 BPM score, original SFX and stock Kokoro 60/40 af_heart+af_bella narration: **−15.00 LUFS / −1.50 dBTP PCM**. Music bed **−22.0 LUFS**, ducked under the voice. Drop at 20.00s (5 ms earlier offset applied to the stems; the finished mix transient lands at 20.001s). All 12 narration cues match the SRT and finish within their allotted scene windows.

## Remaining production inputs

The eight real screen recordings, including the integrated custom guest and human/agent posts on one BBS board. README documents exact paths and capture requirements. All Terry loops and both verbatim quote cues are complete. No connected desktop browser was available for subjective listening; the landscape preview was tested programmatically through complete playback.

## Encoded delivery

All files are H.264/yuv420p + AAC, faststart, 30fps, exactly 2,700 picture frames / 90 seconds. Full video/audio decoding passed for all four exports. AAC makes each compact-preview container 90.005 seconds; picture duration remains exactly 90 seconds.

| Committed file under `preview/` | Dimensions | Bytes | Encoded LUFS | True peak |
|---|---|---:|---:|---:|
| `submission-placeholder-1080p.mp4` | 1920×1080 | 16,017,714 | −15.02 | −2.61 dBTP |
| `submission-placeholder.mp4` | 1280×720 | 6,430,981 | −15.06 | −1.63 dBTP |
| `submission-placeholder-vertical-1080p.mp4` | 1080×1920 | 18,179,664 | −15.02 | −2.61 dBTP |
| `submission-placeholder-vertical.mp4` | 720×1280 | 7,276,460 | −15.06 | −1.63 dBTP |

Actual encoded scene contact sheets reviewed in both aspect ratios. Landscape cut −1/0/+1 frames inspected; motion checks changed pixels in every non-memorial shot. The 87–89s memorial hold differs by only 0.000225 mean channel values after encoding. Opening, typing, quote CTA and dense BBS retain their intended composition.

Landscape 720p preview: full unmuted browser playback reached the end with **2,700 displayed frames, zero dropped frames, zero waiting events and no page/player errors**. Seeking to 70 seconds passed. This is programmatic playback verification, not a subjective audio audition. Portrait exports received full decode and encoded-frame review, not a second realtime playback run.

Clean reproduction: copied source/assets into an isolated directory, installed with `npm ci`, and rebuilt both formats without pre-existing dependencies or decoded caches. Both build fingerprints exactly match the rendered builds:

- Landscape: `049f89288efc179c30a1cdedca3cc00945bcb67c88a18eef81138549511f5640`
- Portrait: `27db75d780f1af5079f2a48d7c0f817e4d7530b0b5c19bfa982aa3953b088ea8`

Measured file checksums, decode evidence, seek checks and playback results are in `preview/verification.json`. Source audit checks the video-only branch scope, every file below 50 MB, exact memorial/footage paths, common secret/private-address signatures, byte-identical quote catalogue and six original loop hashes. No live QEMU or BBS behavior is claimed tested.
