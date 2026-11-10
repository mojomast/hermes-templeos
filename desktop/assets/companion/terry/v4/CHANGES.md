# Revision 4 — smoother arm motion

- Smoking now follows an outward wrist arc around the shoulder, avoiding the elbow solver's abrupt reversal near the shoulder. The cigarette remains attached to the pinch and reaches the mouth.
- Greeting and celebration raises use longer, gentler transitions with more natural elbow flex; the fixed-layout jumping row uses the revised celebration poses.
- Audited all 20 baked animations for frame-to-frame arm motion and joint attachment. `MOTION-CHECK.json` records the measurements; `QA-V4.json` reports geometry and identity checks. Review in the Hermes host remains recommended.

- Anchored the cigarette to the hand’s pinch point throughout smoking, exhaling and other poses with a pinching hand. During inhale, the arm brings the attached filter to the mouth; the prop no longer slides independently.
- Split the original cigarette art into aligned near/far layers at the pinch, letting the fingers cover the grip while keeping the end visible. The existing cigarette canvas and pivot are unchanged; `cigarette_front` is an additive slot.
- Rebuilt all four compatible atlases, 60 fps poses, strips and smoke previews. Approved faces and existing slot pivots remain unchanged.
- `GRIP-CHECK.json` checks attachment through every applicable baked frame; `QA-V4.json` contains independent geometry and identity checks. Inspect the revised art in the Hermes host.

# Revision 3 — cigarette grip

- Anchored the cigarette to the hand’s pinch point throughout smoking, exhaling and other poses with a pinching hand. During inhale, the arm brings the attached filter to the mouth; the prop no longer slides independently.
- Split the original cigarette art into aligned near/far layers at the pinch, letting the fingers cover the grip while keeping the end visible. The existing cigarette canvas and pivot are unchanged; `cigarette_front` is an additive slot.
- Rebuilt all four compatible atlases, 60 fps poses, strips and smoke previews. Approved faces and existing slot pivots remain unchanged.
- `GRIP-CHECK.json` checks attachment through every applicable baked frame; `QA-V3.json` contains independent geometry and identity checks. Inspect the revised art in the Hermes host.

# Terry companion â€” art revision 2

- Preserved the approved 2017 face plates byte for byte. Added a shared GPT-generated salt-and-pepper chin/jaw overlay for better small-size readability; the upper lip stays clear.
- Smoking and exhaling now explicitly tuck the keyboard under the far arm. The cigarette hand approaches from outside the cheek, with continuous rotation and a mouth-aligned filter.
- Smoke is a separate rear layer. Wisps stop during the approach and inhale; the exhale starts after the hand has withdrawn. Smoke anchors follow the rig at birth, then particles drift independently.
- Added six presets: `vm_booting`, `celebrate_short`, `greet`, `nod`, `stretch`, and `relieved`. There are now 20 presets, including the existing dance, typing, speech and smoking clips.
- New motions use fixed ankle targets, anticipation and recovery. The success row has a small cushioned jump; the failure row now returns smoothly from its lean.
- Supplied 60 fps solved poses. Interpolation happens before limb solving, so elbows and wrists remain connected. The reference player holds each complete solved pose and clamps one-shot clips at their end.
- Retained all slot sizes/pivots, four atlas filenames, 1536Ã—1872 dimensions, nine-row layout, 192Ã—208 cells and y=198 standing soles. Cleared transparent RGB and removed the shadow's previously clipped bottom row.

Use `INTEGRATION-V2.md` for replacement paths, new motion timing and compositing instructions. The new optional presets are separate from the fixed nine atlas rows; adding them to Hermes hook behavior requires the integrating agent to wire them in.

The optional profile/three-quarter turnaround is deferred. The approved frontal likeness remains the only active head orientation.

Original fan tribute to Terry A. Davis. No official TempleOS affiliation and no invented quotes.
