> Revision 3: cigarette and `cigarette_front` share an identical transform. Draw `cigarette` (filter) behind the boosted near hand and `cigarette_front` (distal section) above it. Both parts are cropped from the same source and must be kept together. `cigarette_grip` is a hand-local attachment resolved into world coordinates; never interpolate the prop separately from the hand. See GRIP-CHECK.json.

> Revision 3: cigarette and `cigarette_front` share an identical transform. Draw `cigarette` (filter) behind the boosted near hand and `cigarette_front` (distal section) above it. Both parts are cropped from the same source and must be kept together. `cigarette_grip` is a hand-local attachment resolved into world coordinates; never interpolate the prop separately from the hand. See GRIP-CHECK.json.

# Revision 2 integration

This is an art and reference-animation handoff. It does not change the Hermes plugin, its default-enabled setting, hooks, configuration or preferences.

## Drop-in atlases

Replace the same files used by the original handoff:

| Costume | Image | Metadata |
| --- | --- | --- |
| Base | `modular/out/atlas.png` | `modular/out/atlas.json` |
| Cowboy | `modular/out/cowboy/atlas.png` | `modular/out/cowboy/atlas.json` |
| Wizard | `modular/out/wizard/atlas.png` | `modular/out/wizard/atlas.json` |
| Chef | `modular/out/chef/atlas.png` | `modular/out/chef/atlas.json` |

All retain 8×9 cells of 192×208, total 1536×1872. Row order and counts remain idle 6, running-right 8, running-left 8, waving 6, jumping 6, failed 6, waiting 6, running 6, review 6. The row period remains 1100 ms. Standing soles remain at y=198; airborne frames deliberately release contact. Slot canvases and pivots are unchanged.

The existing atlas-only host benefits from stronger stubble, cleaner fallback smoke layering, a revised success jump and a closed failure reaction. Smoking, exhaling and the six new rich motions live in the separate modular presets; replacing the four atlases alone does not add new host states.

## Complete motion poses

`modular/presets/*.json` are editable source controls. `modular/baked-presets.json` has 20 clips sampled at 60 fps, including the nine standard states. Every baked frame includes all visible parts, their world-space transforms, named joints and explicit attachment state. They already include 0.9 root scaling and floor alignment: do not apply those a second time.

Use the supplied reference player or select a complete baked frame from elapsed time. Do not interpolate a solved elbow position and its parent rotation independently: that separates the segments. For new in-between poses, interpolate source targets/angles with `scripts/sample_motion.py`, then call `scripts/rig.py:expand_frame`. Keep IK bend signs stable.

For a looping clip, wrap time and index across N frames. For `loop:false`, clamp time and map it across N−1 intervals, including the final endpoint. Loops exclude a duplicated endpoint. Each PNG pose strip has accompanying timing metadata; the GIFs are 20 fps inspection previews, while the baked JSON is the higher-frequency source for playback.

| New preset | Duration | Behavior |
| --- | ---: | --- |
| vm_booting | 3600 ms | Loop; brief alternating taps, watch and repeat |
| celebrate_short | 1800 ms | One shot; anticipation, jump, landing, settle |
| greet | 2400 ms | One shot; shoulder raise, wrist waves, lower |
| nod | 1200 ms | One shot; small acknowledgement |
| stretch | 3400 ms | One shot; both arms rise, hold and recover |
| relieved | 2400 ms | One shot; shoulders release and expression settles |

Smoking is a 5600 ms loop. Exhaling is a 3200 ms one-shot. Preserve these durations; they are not 1100 ms atlas rows. The original dance remains 7200 ms. Speech still needs actual audio/TTS timestamps for synchronized dialogue.

## Keyboard, hand and smoke

Apply a whole frame on every state change; clear old attachments first when `reset_attachments` is set. Honor `hidden_slots`, alpha and `keyboard_disposition`. Smoking/exhaling explicitly place the keyboard nearly vertical under the far arm and behind its sleeve. Typing/VM booting put it across the front with hands above the keys.

The cigarette's filter and tip are separate named joints. The pinching fingers overlap the cigarette at its grip. Preserve the two cigarette layers and the hand layer boost; the hand comes in front of the face during the inhale.

Use `frame.emitter.origin_joint`, `start_offset`, `type` and `active`. The `mouth` and `cigarette_tip` positions include the same scale and floor alignment as the body. Draw the smoke particle pass before the character, then draw solid body/head/hand layers. Do not bake wisps over the face or place smoke above the face again in a second pass.

Spawn particles at their world position and let them keep that position after birth. Use the existing smoke textures and seeded recipes. Stop new births during approach/inhale, retain fading particles, and begin the exhale after withdrawal. Use source-over alpha. The demo's manual smoke controls deliberately override automatic timing for inspection.

## Likeness and testing

All approved 64×84 head plates are unchanged. The shared stubble slot adds lower-cheek/chin coverage without modifying the eyes, nose, jaw silhouette or upper lip. Keep the head rigid; use discrete expression plates to avoid ghosted eyes or mouth shapes. No side-view face is enabled in this revision.

`QA-V2.json` contains independent geometry, transparency, slot, prop and joint checks across all four costumes and source/baked clips. `RUNTIME-CHECK.json` checks reference-renderer paths, math, props and one-shot endpoints. The output proofs include smoking across costumes, stubble comparison, new motion contact sheets and GIFs. Numerical mock-Canvas checks do not replace a browser/host visual check of this revision.

Recommended host check: switch typing → smoking → exhaling → typing; inspect the keyboard position, cheek overlap and emitter birth point at normal scale on dark/light panes. Try every costume, pause at the jump apex, and verify one-shots settle instead of wrapping unexpectedly.

The earlier `INTEGRATION.md` retains the research links and general rigging guide. Revision 2 overrides its older advice about interpolating baked transforms and drawing smoke last.

Original fan tribute. No official TempleOS affiliation; no invented dialogue.
