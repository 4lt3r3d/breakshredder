# How to add, change and swap instruments

For the next AI working on BREAKSHREDDER. Written 2026-11-17 at the user's request: they want to keep adding instruments and swapping instruments out, and this is the map for doing that without breaking anything.

Read `HANDOFF.md` first (rules, history, what the user has and has not heard). This file is only about instruments. Line numbers are not given because they drift; search for the names in `code font`.

## The five things to know before touching anything

1. **Every sound exists twice.** The live preview is Web Audio in `index.html`; the export is numpy in `render.py`. Same formula, same constants, same defaults in both. If you change one and not the other, the user hears one thing and exports another. This is the rule most easily broken.
2. **Nothing is decided at playback.** `Generate` writes an explicit edit list (`eng.edl` in the page; saved as `<name>.edl.json` beside every export). Preview and export both just play that list. Anything that changes WHICH notes play or WHEN must be written into the edit list (see `applyRetrig` for the pattern), never worked out separately in the two players.
3. **Sound settings are read at playback, not baked into notes.** Mixer levels (`mix`), sound panels (`snd`) and switches (`mute`) sit at the top of the edit list. Changing them must never regenerate the arrangement.
4. **The source comes first.** The user's rule: the video's own audio supplies the music. Bass, reese, acid and melody are source slices, processed. Plain oscillators are an optional extra behind the Synth switch (off by default). The added drum kit is the one agreed exception: it plays the user's own samples from `drumnbasskit/` and is also off by default. Before making any other instrument out of something that is not the source, ASK the user.
5. **Restart.** A running `start.bat` keeps the old `app.py` and `render.py` in memory while `index.html` is read fresh. This silently broke the drums for the user for hours (see "The stale-server trap" in `HANDOFF.md`). After changing `app.py` or `render.py`, tell the user FIRST and on its own line: close the black window, run `start.bat` again, refresh. The page now also warns ("Restart needed - see log").

## The three kinds of instrument

| Kind | Members | Lives in the edit list as | Played by (page / export) |
|---|---|---|---|
| **Samples** (the chopped video audio itself) | KICK, SNARE, HAT, TONAL | `bar.events[]`: `{ t, d, s, role, g, rate, rate2?, rev?, op, grain?, seed? }` | `scheduleEvent` + `voice` / the first big loop in `render()` |
| **Source-made pitched instruments** | SUB, REESE, BOX (music box), ACID | `bar.synth[]`, a note WITH `s`: `{ t, d, voice, s, rate, rate0?, g, acc?, rt? }` | `playNote` -> `scheduleSynth` / the `for e in synth:` loop |
| **Synth layer** (optional oscillators) | the same four voices | `bar.synth[]`, a note WITHOUT `s`: `{ t, d, voice, note, from?, cents?, g, acc? }` | the same functions, the `clip` is null / `clip is None` branch |
| **Added drums** (the user's samples) | K kick, S snare, L clap, C closed hat, O open hat, P and Q percs | `bar.drums[]`: `{ t, drum, g, s?, d? }` | `scheduleDrum` / the "Added drum kit" block |

Times (`t`, `d`, `rt`) are in BEATS from the start of the bar. `s` is a slice number of the analysed video.

How the mixer sees them (the user's own grouping, by musical role): **Samples** = the first row. **Instruments** = source-made instruments + Synth layer + added drums. **Master** = everything.

## Where each thing is defined (both files unless marked)

| What | Page (`index.html`) | Export (`render.py`) |
|---|---|---|
| On/off switches, in order | `INSTRUMENTS` list | reads `edl.mute` |
| Mixer sliders | `MIXER` list, `eng.mix` defaults, `buildBus` (the list of names connected to `b.instruments`) | `level(mix.get(...))` where bars are flattened; the `mixer:` log line |
| Sound panel controls | `SND` (own controls), `SND_NOTE` (per-note row), `SND_EXTRA` (overflow), `SND_FX` (effects row), `SND_HELP` (tooltips), `SND_ROWS` (layout) | `SND`, `SND_NOTE`, `SND_FX` as dicts `key: (lowest, highest, default)` |
| Turning saved settings into numbers | `sound(voice, plain)` | `sound(snd, voice, plain)` |
| Which slice each source-made instrument plays | `buildKit` -> `kit.src`, via `tuned(slice, octave, level)` | nothing: it is baked into each note as `s`, `rate`, `g` |
| The notes | `genBar`: `subLine`, `reeseLine`, `boxLine`, `acidLine`, then `layer()` | nothing |
| The drum pattern | `genBar`: `drumLine` | nothing |
| How a source slice is played (start, reverse, loop, bend, stretch) | `src()` inside `scheduleSynth` | `voiced()` |
| Per-instrument channel (drive on kit, bits+rate, delay, reverb) | `applySnd`, `eng.inp` / `eng.post` / `eng.fx` | `emit()` collects into `chan`, then the "Channel effects" loop |
| Drum kit files | `DRUM_PICK`, `DRUM_LEVEL`, `DRUM_G`, `loadDrum`, `loadKitList` | `KIT_DIR`, `KIT_FILES`, `DRUM_PICK`, `DRUM_LEVEL`, `DRUM_G`, `kit_path`, `kit_counts` |
| Serving kit files to the page | (server, `app.py`) `/api/kit`, `/kit/<letter>/<n>.wav` | |

A sound-panel control is one array: `[key, label, lowest, highest, step, default, unit, logSlider?]`. The same key, limits and default must appear in `render.py`'s table.

## Recipes

Do ONE recipe at a time, then let the user listen (their rule).

### A. Swap which SOURCE SLICE an instrument uses
Only the page. In `buildKit`, near the end: a pool of the 12 best tonal/vocal slices is built (`score` = loudness x length x how un-percussive; locked slices first). `bass` = the darkest (lowest spectral centroid), `bell` = the brightest, `lead` = the best of the rest. Then:

`kit.src = { SUB: tuned(bass, -1, 1.2), REESE: tuned(bass, 0, 0.8), ACID: tuned(lead, 0, 0.3), BOX: tuned(bell, 1, 0.9) }`

`tuned(slice, octave, level)`: transposes the slice so its own note lands on the root (the analysis only knows a slice's note NAME, not its octave, so tuning is approximate), adds the octave, and sets its level against the drums.
- To give an instrument a different slice: change the selection (`bass` / `lead` / `bell`), or add a new pick from `pool`.
- To let the USER choose: today they steer it only by locking slices in the slice bank. A real chooser would store a slice number per instrument (for example `eng.pick[voice]`, saved in the edit list) and use it in `buildKit` when set. Not built.
- A different slice per section, or several slices per instrument, would go in `layer()`, which is where each note gets its `s`.

No `render.py` change is needed for any of this: slice, rate and level are already in each note.

### B. Change how an existing instrument SOUNDS by default
Change the default (6th item) of its controls in `SND` in the page and the matching tuple in `render.py`. Know that:
- "Bypass" on a panel means "the default sound", and so does an older edit list with no `snd`. Changing a default changes both.
- The Synth layer's oscillators use the defaults too (`plain`). If the Synth version must stay as it is, pin its old values in `SND_OSC` in BOTH files (see ACID, which was made bigger by default while its oscillator was left alone).
- An instrument-specific default for a shared effects-row control: see `ACID_FX_DEFAULTS` (page) and `SND["ACID"].update(...)` (export).
- If the change makes it louder or quieter, measure (see "Testing") and correct the level, either in `tuned(...)` or with an output constant like `ACID_OUT`.

### C. Add a CONTROL to an existing instrument
1. Add the array to that instrument in `SND` (or `SND_EXTRA` if its first row already has 6). Pick a key that is not used with another meaning: `cut` is Cutoff on instruments but "Cut picture" on the drums; `rev` is Reverb, so Reverse is `back`.
2. Add a tooltip in `SND_HELP`.
3. Use `P.<key>` in that instrument's branch of `scheduleSynth` (or in `src()` if it concerns how the slice is read).
4. Add `"key": (lowest, highest, default)` to `SND[...]` in `render.py` and use `P["key"]` in the matching branch (or in `voiced()`).
5. The default must reproduce today's sound exactly (so nothing changes until the user moves it), unless the user asked for a new default.
6. Apply it to source notes only unless the user wants the Synth layer changed: in the page use `clip ? P.key : <neutral>`, in the export `P["key"] if clip is not None else <neutral>`.
7. If it changes timing or which notes play, do not compute it at playback: write it into the notes like `applyRetrig` does, and expand it identically in `playNote` and where `render.py` flattens the bars.

### D. Add a NEW source-made pitched instrument
Example name `PAD`. Touch points, in order:

Page:
1. `INSTRUMENTS`: add `["PAD", "Pad"]` (before `SYNTH`). This creates its switch.
2. `MIXER`: add `["PAD", "Pad", ""]`; add `PAD: 100` to `eng.mix`; add `"PAD"` to the list in `buildBus` that is connected to `b.instruments`.
3. `SRC_BASE`: add the note (semitones above the root) at which its slice plays untransposed.
4. `SND`: add `PAD: [ ...its own controls... ]` BEFORE the loop that appends `SND_NOTE` and `SND_FX`, so it gets the note row and effects row automatically. This also creates its Sound panel and its mixer channel (`eng.inp.PAD`, `eng.post.PAD`), because those are built from the keys of `SND`.
5. `buildKit`: add `PAD: tuned(<slice>, <octave>, <level>)` to `kit.src`.
6. `genBar`: write `padLine(bar)` returning oscillator-style notes `{ t, d, voice: "PAD", note, g }`, with its OWN random stream (`rng32((barSeed(eng.seed, n, regen) ^ 0x........) >>> 0)`, a new constant) so it never changes the other parts. Add it to the `layer(...)` call for the sections where it should play. `layer()` then writes the source version of every note automatically.
7. `scheduleSynth`: add an `if (e.voice === "PAD") { ... return; }` branch. Model it on REESE (sustained) or BOX (struck). Use `src(rateFrom, rateTo, slideSeconds, intoNode)` for the slice and `osc(...)` for the Synth version; finish with `.connect(desk)`.
8. `drawBar` needs nothing (all `synth` notes draw as the bottom strip).

Export:
9. `SND["PAD"] = {...}` with the same keys, limits and defaults, placed before the loop that adds `SND_NOTE` / `SND_FX`.
10. In the `for e in synth:` loop add `elif voice == "PAD":`, mirroring the page branch: `voiced(clip, P, n, dur, rate0, rate, slide)` for the slice, then filter / envelope, then `emit(e, block, P)`. `emit` handles the mixer level and the channel effects.
11. Add `"PAD"` to the names in the `mixer:` log line.

Then: add `"PAD"` to `INSTRUMENTS` in `tests/check_sound.py`, restart the server, and test.

Old edit lists have no PAD notes and no `mix.PAD`; both are handled (no notes = silent, missing level = 100).

### E. Change the ADDED DRUMS
- **Different sample by default**: change the default of `ksel` / `ssel` / `lsel` / `csel` / `osel` / `psel` / `qsel` in `SND.DRUMS` (page) and `SND["DRUMS"]` (export). The user can already pick any numbered file with the sliders.
- **Different files in the same folders**: nothing to change. Files are found by name: `drumnbasskit/<folder>/<name> <number>.wav`, numbered from 1 with no gaps. The sliders stop at however many there are.
- **A different kit folder or layout**: `KIT_DIR` and `KIT_FILES` in `render.py` are the ONLY place that knows the layout (`app.py` asks `render.kit_path` / `render.kit_counts`). A second selectable kit would need a kit name in the saved settings and in `kit_path`.
- **A new drum** (example: a ride, letter `R`): add `"R": ("<folder>", "<file name stem>")` to `KIT_FILES`; add `R` to `DRUM_PICK`, `DRUM_LEVEL`, `DRUM_G` in BOTH files; add a level control and a sample control to `SND.DRUMS` / `SND["DRUMS"]` and adjust `DRUM_ROWS` (page layout: controls per row); write hits `{ t, drum: "R", g }` in `drumLine`. `scheduleDrum` and the export block are table-driven, so they need no change unless the drum needs special treatment (as the open hat's cut-off `d` does).
- **The pattern**: `drumLine` in `genBar`. The kick on steps 0 and 10 and the snare on 4 and 12 are deliberately fixed. The groove around them comes from a stream that repeats every two bars inside a section; only fills are decided per bar. It deliberately ignores the Intensity slider.
- **The picture**: only K and S hits carry `s` (a source slice to show) and only they cut the video, and only when "Cut picture" is on.
- Do NOT bring back a synthesized drum kit. The user rejected it ("horrible").

### F. Swap an instrument OUT for something else
Decide which of these the user means, and ask if it is not clear:
- **A different sound from the same source** -> recipe A (other slice) and/or B (other processing). No new instrument.
- **Replace the source-made version with a sample from `drumnbasskit/`** (the folder also holds `subs & basses/bass N.wav`, `sub N.wav`, `pads and one shots/pad N.wav`, `one shot N.wav`, all unused so far). This goes against rule 4, so confirm first. If they want it: the cleanest way is a second SOURCE OF AUDIO for a note, not a new instrument. Give `kit.src[voice]` an optional kit reference, write it into the notes in `layer()` (for example `k: "bass 3"` instead of `s`), and in `src()` / `voiced()` load that file instead of the slice (page: the same fetch-and-cache as `loadDrum`, with a new letter in `KIT_FILES`; export: `soundfile.read`, as the drum block does). Everything after that (filters, envelopes, panel, effects, mixer) stays as it is. Tuning: these files have no analysed note, so add a tune control or assume the sample is at a known note.
- **Remove an instrument**: take it out of `INSTRUMENTS`, `MIXER`, `eng.mix`, the `buildBus` list, `SND`, `SRC_BASE`, `kit.src` and the `layer(...)` call in the page, and its `SND` entry in `render.py`. Leave its `scheduleSynth` / export branch in place or delete both together. Old edit lists that still contain its notes must not crash: both players already skip a voice that is not in `SND`.
- **Hide it but keep it**: simplest of all, add it to the default `eng.mute` (like `SYNTH: true, DRUMS: true`).

### G. Change the SAMPLES row (kick, snare, hat, tonal slices)
These are not "instruments" in the mixer sense. Which slices play each role is `buildKit` (top half: tags from the analysis, user overrides and locks from the slice bank). How they are chopped up is the main body of `genBar`. They also drive the picture, so changes here change the video.

## Testing a change

1. `python tests\\check_sound.py renders\\<a recent name>.edl.json` (the edit list must be from the current page: Generate, then any Export). It checks that the export is deterministic, prints how loud each part is alone, checks the mixer scales each part exactly, and checks that Bypass equals the default. Add a new instrument's name to `INSTRUMENTS` at the top of that file.
2. In the page: Generate twice with the same seed and compare `JSON.stringify(BREAKSHREDDER.edl().bars)` in the console (must be equal); play with the new thing on and with its controls at both ends; check the console for errors.
3. A full export from the page, to see the settings arrive in `<name>.log.txt`.
4. Levels as a rough guide (loudest bar, each part alone, test video): chopped video audio 0.22, sub bass 0.15, acid 0.16, added drums 0.15, reese 0.09, music box 0.04.
5. What a script cannot tell you: whether it sounds good, and whether preview and export sound the same. Say so to the user. The preview's audio has never been captured and compared.

`.claude/launch.json` starts a test copy of the server on port 5079 without opening the user's browser; the user's own `start.bat` uses 5077. Stop the test copy when done.

## Mistakes already made here (so you do not repeat them)

- A level multiplied in BEFORE distortion in the export but after it in the page: the two distorted differently whenever a mixer slider was not at 100. Mixer levels must be applied after all of an instrument's own processing (`mg` in `render.py`, `eng.bus[...]` in the page).
- A variable named `total` reused inside the effects code overwrote the song length. `render()` is one long function: check a name is free before using it.
- A panel-drawing bug from using a variable before it was assigned made a whole panel fail silently. Open every panel after touching `paintSound`.
- Labels: a control key reused with another meaning showed "On" for a cutoff. Check the value text of every control you add.
- Resonance without level compensation was eight times louder at the top of its range. Sweep every new control to both ends and measure.
- Default changes are not free: they change Bypass, old edit lists and (unless pinned in `SND_OSC`) the Synth layer.
- UI: three colours, no clutter, expandable panels, 6 controls per row. See "Look" in `HANDOFF.md`.
