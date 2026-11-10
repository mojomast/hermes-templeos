REVISION 4: Smoother elbows, greeting and celebration. See CHANGES.md and GRIP-CHECK.json.

REVISION 3: Cigarette grip and mouth placement corrected. See CHANGES.md and GRIP-CHECK.json.

TERRY COMPANION — REVISION 2 ASSET HANDOFF

Start with INTEGRATION-V2.md and CHANGES.md. Open runtime/demo.html to browse the animations,
costumes, speech shapes and layered smoke. The demo uses local images and
classic JavaScript; it requires no external libraries or account.

Included
  - 54 GPT-generated illustration/VFX source masters and final prompt records.
  - 18 distinct whole-head expression/speech plates, plus default=neutral.
  - Separate backwards cap and three costume packs: cowboy, wizard, chef.
  - Jointed arms and legs; five interchangeable hand poses.
  - Eight separate smoke textures, four emission recipes and animated proofs.
  - Four validated 1536x1872 Hermes atlases, 58 active frames in each.
  - Twenty reusable animation presets, including typing, talking, smoking,
    exhaling and a 7.2-second adaptation of the requested dance.
  - A separate 72-frame dance sheet and smooth animated dance preview.
  - Editable rig inputs, baked transforms, Python compositor, reference
    JavaScript renderer, integration guidance, sources and validation tools.

Important files
  INTEGRATION.md                    Practical handoff with research links.
  modular/parts.json                 Slot canvases, pivots and layer order.
  modular/rig.json                   Joint and root-scale contract.
  modular/anims/                     Fixed nine-state Hermes animation rows.
  modular/presets/                   Additional editable rig animation clips.
  modular/baked-presets.json         Precomputed part transforms for 20 clips.
  modular/speech.json                Viseme mapping and sample timed events.
  modular/out/atlas.png + atlas.json Base Hermes atlas and row metadata.
  modular/out/{cowboy,wizard,chef}/   Costume atlases and metadata.
  modular/out/face-compare.jpg        All expression and speech plates.
  modular/out/head-cap-check.jpg     Bare and capped head combinations.
  modular/out/motion-v2-contact.jpg     Typing, speaking, smoking, exhaling proofs.
  modular/out/presets/dance.gif      The requested dance adaptation.
  modular/out/presets/dance-sheet.*  Transparent dance frames and timing.
  modular/out/masters/               High-resolution generated sources.
  smoke/smoke.json                   Texture anchors and emitter recipes.
  smoke/smoke-preview.gif            Layered wisps and exhale-burst preview.
  runtime/demo.html                  Interactive handoff demo.
  VALIDATION.json                    Image/atlas/pose checks.
  RUNTIME-CHECK.json                 Numerical renderer and asset-path checks.
  generation-prompts.json            Final prompt set and portable master paths.
  SHA256SUMS.txt                     File integrity manifest.

Rebuild with Python 3.10+ and Pillow/numpy from requirements.txt:
  python modular/compose.py --costume base
  python modular/compose.py --costume cowboy
  python modular/compose.py --costume wizard
  python modular/compose.py --costume chef
  python tools/rebake_presets.py
  python tools/rebake_presets.py
  python tools/rebake_presets.py
  python tools/validate_package.py --report QA-V2.json --report QA-V2.json --report QA-V2.json

Optional reference-renderer checks with Node 20+:
  node tools/check_runtime.cjs

The original slot sizes and pivots are retained. The cap attachment moved to
head-local (32,24) and now follows head rotation. New limb segment slots are
additive. The rig applies uniform 0.9 root scale before baseline alignment;
baked poses already include that scale. All standing body soles land at y=198.
The jump apex releases foot lock. The optional three-view head turnaround
was not produced. The approved frontal face is used throughout the dance.

Speech timing is an illustrative animation, not synchronized to supplied
audio. Use real audio/TTS timing when integrating. Hand plates support wrist
and elbow articulation; they do not include separate finger bones.

Browser policy blocked local-file navigation during this session. Rendered
PNG/GIF proofs were visually inspected, and the JavaScript received numerical
and asset-loading checks with a mock Canvas; the demo still needs a real
browser/host-app check. No Hermes plugin code, publishing or event wiring was
performed. This package is the artwork and integration handoff.

Original fan-made tribute inspired by Terry A. Davis. No official TempleOS
affiliation is claimed. Reference photographs and the original dance GIF are
not redistributed. Original handoff compositor source is retained with its
headers. Generation used the available built-in GPT image capability; its
exact model version was not exposed.

V2: six new motions, under-arm keyboard carry while smoking, rear smoke,
stronger shared stubble, intact60fps solved poses and unchanged approved heads.
Optional turnaround remains deferred. New presets require host event wiring.

V2: six new motions, under-arm keyboard carry while smoking, rear smoke,
stronger shared stubble, intact60fps solved poses and unchanged approved heads.
Optional turnaround remains deferred. New presets require host event wiring.

V2: six new motions, under-arm keyboard carry while smoking, rear smoke,
stronger shared stubble, intact60fps solved poses and unchanged approved heads.
Optional turnaround remains deferred. New presets require host event wiring.
