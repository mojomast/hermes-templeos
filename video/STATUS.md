# Submission production checkpoint

Branch `video/submission`, based on updated `feat/plugin-integration` at `0f50faac279f7a669e66a13d0b1ce881a7a86917`. Initial source was `e16c9e7`; the unpublished local branch was advanced with `git reset --keep` after verifying it contained only untracked video work. OS research remains `hermes/readme` at `44d4c542d64b40513a635494ac791d281b748fc4`.

Contract: Hyperrizz/HyperFrames source and placeholder preview, 90s / 1080p30 plus portrait, all changes under video/, every committed file <50 MB, push only video/submission. No fake UI or made-up quotes.

The six missing HD loops and quote catalogue arrived on the updated integration branch. Exact VP9 sources and catalogue are copied under video/assets/terry/. Quote IDs are JSON Pointers #/19 (opening) and #/6 (closing), because upstream has no id fields. README screenshot contains #/32. All eight live footage captures remain missing and visibly labelled. Current flavor table still defaults to TinkerOS; final custom-guest/relay capture remains a separate input.

Landscape/portrait preflight passed after integrating the actual HD loops. Forty reverse and shuffled exact-pixel matches each; landscape 1,045 / portrait 1,082 typography checks, no errors. All six loop hashes and all-frame head-alpha coverage checked. Exact copy and shot docs updated.

Production pipeline `sh_1cb6011eb001BXKHWTIao5m0CD` completed successfully. No active render. Four verified MP4s are in preview/: landscape 1080p / 720p and portrait 1080×1920 / 720×1280. Every file is below 50 MB. Encoded stills and both contact sheets inspected; landscape full playback passed with zero drops/stalls/errors. Source-only clean rebuild fingerprints match both rendered builds. See REVIEW.md and preview/verification.json for exact measurements and checksums.

Remaining content work: replace the eight live-footage slots, verify actual integrated guest/BBS capture, and render with `--final`. The supplied quote/loop assets are complete. Subjective audio audition remains unperformed.

The user subsequently requested a private Tailscale review. Its dedicated server runs outside the repository; address and runtime ownership are recorded only in ignored local handoff state. Branch delivery is limited to video/submission; no merge, tag or force-push is part of this task.
