# One Live Screen — MorningDAW project

Reproducible 120 BPM score for the submission film, in D minor, seed 1.

The `.mdproject` is a MorningDAW 1.6.3 song file. It references factory drum
samples by path from a local MorningDAW install and stores Surge XT patch
state for the instruments. It does **not** bundle MorningDAW binaries, factory
presets, or samples (MorningDAW is proprietary freeware from Morningdew Media
AB). To rebuild, install MorningDAW, Surge XT, Dragonfly Reverb and Airwindows
Consolidated, then run `python3 video/scripts/music.py --rebuild-score` from
the `video/` directory. `scripts/music.py` calls the `mdaw` package from
[hermes-morningdaw](https://github.com/mojomast/hermes-morningdaw) with the
same argument dicts as the plugin tools.

Form (45 bars of music plus a 3-bar reverb tail, 96 s before trim):

- Intro — 10 bars, pad and arp, hats
- Drop — 16 bars, pad, bass, arp and stab, four-on-the-floor (starts at 20 s)
- Break — 8 bars, pad and a quieter lead, hats
- Hook — 8 bars, all parts, four-on-the-floor
- Outro — 3 bars, pad, a single drum hit on each bar
- Tail — 3 bars, pad only, no drums

Sections are stored as patterns of at most 64 rows (4 bars at LPB 4), which is
what MorningDAW plays reliably. The chord loop is Dm–Bb–F–C, one chord per bar.

Instruments (Surge XT factory patches): choir pad, Bell 1 arp, Sub 2 bass,
Organ 1 stabs, Sine Lead with a small `a_portamento`. Effects: Dragonfly Hall
on pad and bells, Dragonfly Room on snare pad 40, Airwindows ToTape6 on the
master. `ab_check.json` records that every effect changed the output.
