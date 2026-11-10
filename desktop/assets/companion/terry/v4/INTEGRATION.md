> Revision 2: read INTEGRATION-V2.md first. It overrides old interpolation and smoke-layer advice below.

> Revision 2: read INTEGRATION-V2.md first. It overrides old interpolation and smoke-layer advice below.

> Revision 2: read INTEGRATION-V2.md first. It overrides old interpolation and smoke-layer advice below.

# Terry companion: integration handoff

This is original fan-made artwork for the companion feature inside TempleOS
Hermes. It is not a standalone plugin or an official TempleOS product.
The 2017 photo-based neutral face was approved by the user during production.
Keep that likeness. Costumes replace hats and add clothing; they never redraw
the face. The supplied photos are deliberately not redistributed here.

## Start here

1. Open `runtime/demo.html` to inspect the supplied poses, speech and smoke.
2. For the existing Hermes atlas renderer, use `modular/out/atlas.png` and
   `modular/out/atlas.json`. Costume atlases are in named subdirectories.
3. For independent arms/hands and dynamic effects, use `runtime/data.js` with
   `runtime/companion.js`. This reference renderer has no external libraries.
4. `modular/baked-presets.json` contains world-space part transforms: interpolate
   these directly if you do not want to implement a bone hierarchy.
5. `modular/anims/*.json` and `modular/presets/*.json` retain editable shoulder,
   elbow, wrist and hand targets. `modular/scripts/rig.py` expands them.

The demo is a reference and handoff aid. It does not modify Hermes or wire up
its events. Check the target application's asset-loading rules when integrating.

## Dance preset

`presets/dance.json` and the `dance` entry in baked-presets.json provide a
7.2-second loop with 72 editable key poses. `out/presets/dance.gif` previews
smooth interpolation; `dance-sheet.png` and its JSON provide 72 pre-rendered
RGBA frames in an 8-by-9 grid. This separate dance sheet does not replace the
fixed nine-state Hermes atlas.

The motion is an authored stylized adaptation of the side-to-side hip sway,
alternating bent-arm pumps, hand sweeps and small shuffles in the requested
[KLIPY dance reference](https://klipy.com/gifs/terry-davis-terry-1). The original
reference was 72 frames at 100ms each. Feet are partly cropped, so footwork is
interpreted. The approved frontal face is retained with gaze/tilt changes in
place of a newly generated side face. Keyboard and cigarette are hidden for
this two-handed action. The reference GIF is not redistributed.

## Rig and coordinate contract

All character coordinates use a 192 by 208 cell: origin top-left, x right,
y down, angles in degrees clockwise. Each part is drawn with its pivot at
the pose's x,y. Keep the pivot from parts.json when trimming or packing art;
an atlas subrectangle is not a new pivot. Store trim offsets if repacking.

Original slot sizes and pivots are unchanged. New segment slots are additive.
The rig applies a uniform 0.9 root scale about (96,148) before foot alignment,
keeping the standing character near the requested 175px height. This preserves
facial proportions. Baked poses already include it (`global_scale_applied`);
do not scale those poses again. Joint lengths below are unscaled setup units.
Arms: shoulder -> upper arm (24px) -> elbow -> forearm (22px) -> wrist -> hand.
Legs: hip -> thigh (24px) -> knee -> shin (21px) -> ankle -> sneaker.
The two-bone helper clamps unreachable hand targets and uses an explicit bend
sign; preserve that sign over a clip to avoid elbow popping.

Build a pose in this order: reset to setup pose; apply body clip; apply hand
targets/IK; choose head expression; choose costume attachments; calculate all
world transforms; place cigarette and emitters from the resulting joints;
render in slot layer order. Parent transforms must be applied exactly once.

This ordering follows Spine's parent-first world transform model and its use
of bone world positions for attached effects. The included implementation is
an independent, lightweight cutout rig; it is not a Spine-format export.
[Spine runtime skeletons](https://esotericsoftware.com/spine-runtime-skeletons)

Godot's cutout workflow also uses movable pieces, pivots, parenting and IK for
articulated characters. Use a hierarchy if porting to a game engine; the baked
frames are a simpler alternative for the existing flat compositor.
[Godot cutout animation](https://docs.godotengine.org/en/stable/tutorials/animation/cutout_animation.html)

## Hands, typing and cigarette interaction

Use `relaxed`, `grip`, `pinch`, `typing`, and `open` hand attachments.
The opposite hand reuses the same generated art through a local mirror.
The wrist remains the attachment pivot across all hand variants. Do not move
the hand canvas to compensate for a finger shape; change its local pose.

Typing preset: keyboard stays in front of the torso. Both hands have reachable
world-space targets over separate key regions, with small alternating vertical
presses. Target the wrists first, solve elbows, then draw hands above keys.
Do not animate the keyboard with an unrelated sine wave. For future individual
finger animation, add finger attachments; these hand plates do not have finger
bones or independent per-key contact.

Smoking preset: the near hand changes to pinch, lifts toward the mouth, holds,
then lowers. Cigarette filter follows the palm; the source smoke emitter follows
the cigarette tip. Exhale smoke originates at the mouth and is a separate effect.
Keep speech, typing and the hand-at-mouth action mutually exclusive on the same
hand/mouth track. The demo supplies stylized animation timing, not a simulation
of breathing physiology. Smoking is an optional respectful character prop.

The presets contain explicit hand variants and joint locations. No runtime
image generation is required. The original unsplit arms and legs remain as
legacy alternatives; do not draw them together with the segmented limbs.

## Speech without changing identity

Use the supplied whole-head plates as discrete attachments. Never stretch the
head or regenerate a face for every spoken word. The approved neutral is the
identity anchor; eye spacing, nose, jaw, ears and hair should remain fixed.
Inspect expressions at 2x against that anchor if adding new ones.

`speech.json` provides a compact sound-to-plate mapping and illustrative timed
events. Distinct speech plates cover open vowels, rounded vowels, wide vowels,
closed M/B/P lips, F/V, L/TH, S/Z and CH/SH/J, plus a talking blink.
Use audio/TTS viseme timestamps when available, on the audio playback clock.
Do not advance one mouth per rendered frame. Coalesce tiny repeated events;
use neutral during meaningful pauses and stop on neutral when audio ends.
The supplied sample is animation-only, not lip-sync to a particular recording.

Several phonemes can share one visible mouth shape. The included Polly mapping
is deliberately a reduced art mapping, not a claim that each English sound has
a unique plate. Adapt it to the TTS system and language actually in use.
[Amazon Polly visemes](https://docs.aws.amazon.com/polly/latest/dg/viseme.html)
[English sound/viseme table](https://docs.aws.amazon.com/polly/latest/dg/ph-table-english-us.html)

Keep face changes discrete to avoid doubled eyes and translucent jaws during
crossfades. Interpolate source rig controls before solving limbs; select complete solved poses from the v2 baked clips.
For a different mouth shape with a blink, author a corresponding plate; do not
paste a mismatched eye region over the face. `talk_blink` is a supplied example.
Production recommendations here (including transition durations) are choices
for this small sprite, not universal standards.

## Smoke composition

`smoke/assets/*.png` are independent transparent 128x128 textures, not a
sequential flipbook. `smoke/smoke.json` gives each anchor and emitter presets.
The 28x36 smoke slot remains available as a simple atlas-compatible fallback.

Combine a low-density source thread with a few older curl particles. For an
exhale, use a short emission burst of jets/ribbons, then expanding puffs and a
late dissipating cloud. Stagger lifetimes, scale, drift and rotation. Avoid
spawning an identical opaque stack at the same instant. The reference renderer
uses seeded variation and a bounded particle count for repeatable results.

Capture the emitter's world position at birth. Existing particles keep that
position plus their own velocity/acceleration; they do not follow the moving
hand or mouth. Fade in gently and fade out before expiry. Use normal source-over
alpha blending for grey smoke; additive blending would make it glow.

These choices follow the documented particle model of emissions, lifetimes,
parameter variation and independent world-space particles. The exact numeric
presets in this package were authored for Terry's sprite scale.
[Godot 2D particles](https://docs.godotengine.org/en/stable/tutorials/2d/particle_systems_2d.html)

## Layering, transparency and packing

The registry is authoritative for layer order. Far limbs precede torso; near
limbs follow it; typing hands may have a temporary layer boost above keyboard.
Face is above neck; separate hat above face; smoke renders before the character in revision2. Clothing
overlays copy the torso transform, not the head or camera transform.

PNG data is straight/unassociated RGBA. Fully transparent pixels have zero RGB.
Use the alpha convention required by the renderer; do not premultiply twice.
Canvas handles its own upload/compositing. In Pixi/WebGL, distinguish input PNG
data from a texture that is already premultiplied. Configure the actual installed
version's loader accordingly. Inspect against both dark and light backgrounds.
[Pixi alpha modes](https://pixijs.download/dev/docs/rendering.ALPHA_MODES.html)

For optional GPU repacking, keep per-part transparent padding and UV inset or
edge extrusion in the packed GPU texture to prevent neighbor sampling. Keep
the delivered atlas's cleared transparent pixels and required zeroed cell
borders unchanged. Do not blur the entire character to hide seams. Small
overlaps at shoulder/elbow/wrist joints are intentional.

## Timing and state changes

The required nine atlas rows remain 1100ms loops with their original frame
counts. Compute frame duration from loop duration divided by count; do not
assume the eight-frame rows use the same frame duration as six-frame rows.
Keep smoking, typing and richer speech as additional presets, not extra rows
in the fixed Hermes atlas. Jump apex releases foot lock; standing rows use 198.

Use elapsed milliseconds, not frame count. On background/resume, clamp a large
delta and clear stale particles rather than emitting a backlog. Pause all
updates when hidden. Reuse loaded textures and cache image objects.

Body crossfades can be short (about 120ms as a starting point); preserve hand
targets during contact. A whole-sprite crossfade can produce double faces and
props. Spine's animation documentation describes pose mixing; apply the general
idea to transforms, not to blending two visible heads.
[Spine animation mixing](https://eu.esotericsoftware.com/spine-using-runtimes)

## Rebuild and checks

Install Pillow and numpy in your own project environment. Run from the package:

    python modular/compose.py --costume base
    python modular/compose.py --costume cowboy

`anims/*.json` already include the final editable rig overrides. The old
`generate_anims.py` generates legacy starting poses; it is not the authoritative
source for the added rig presets. Back up your changes before regenerating.

Check validate.json and VALIDATION.json. The original optional external
atlasutil module was not in the handoff; the included independent checks cover
geometry, all frames, borders, transparent RGB, and standing body baselines.
The output is an asset package and reference implementation; final event
wiring and checks in the Hermes host remain the integrating agent's work.

The automated browser policy blocked local-file navigation in this session.
PNG/GIF previews were rendered and visually inspected; the JavaScript renderer
received numerical and asset-loading checks using a mock Canvas, not a browser
visual test. The demo is provided for the integrating agent to open and verify.
