# Terry companion atlases

Original fan-made tribute artwork inspired by Terry A. Davis (1969–2018),
author of TempleOS. **No official TempleOS affiliation** is claimed. These
sprites accompany the Hermes TempleOS plugin pane; they are not a standalone
product and invent no quotes.

- Grid: 1536×1872, 8×9 cells of 192×208 (Hermes pet atlas layout).
- Rows: idle, running-right, running-left, waving, jumping, failed, waiting,
  running, review.
- Costumes (`cowboy/`, `wizard/`, `chef/`) replace hats/clothing only; the
  approved ~2017 likeness stays.

Enabled by default in the plugin. Hide in the pane, or set `companion: off` /
`TEMPLEOS_COMPANION=off`.

Revision 2 adds stronger chin/jaw stubble, a cleaner fallback smoke layer, a
cushioned success jump and a smoother failure recovery. Optional rich presets
from the art handoff are not wired into the plugin yet.

Pre-baked v2 motion clips live in `clips/` (base costume only): vm_booting,
celebrate_short, greet, nod, stretch, relieved, typing, talking, smoking,
exhaling, and dance. Costume-specific rich strips were not shipped, to keep
the plugin size reasonable; cowboy/wizard/chef still apply to the nine atlas
rows. Triple-click Terry to dance. Call `TerryCompanion.say(text)` (or POST
`/companion` with `{say}`) for a bubble to his left/above.
