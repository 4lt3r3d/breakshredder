# BREAKSHREDDER handoff

Read this first, then `BUILD_PROMPT.md` (the original full spec). Where the two disagree, this file wins: it records decisions the user made during the build.

## START HERE (state on 2026-11-17, end of the session that built stages 1 to 4)
- All four stages of the user's plan are BUILT: mixer; sound panels with note options and effects on every source-made instrument; an added drum kit playing the user's own samples; three export types. Details are under "CURRENT PLAN".
- What the user has actually judged by ear is very little (see "The stale-server trap"): the acid ("weak" -> made bigger and crushed -> "good for now I guess, we'll change later") and the first synthesized drums ("horrible" -> replaced by their samples). Everything else is technically checked but unheard. Expect listening feedback; take it one item at a time.
- WHAT THE USER WANTS NEXT: to keep ADDING instruments and SWAPPING instruments out. `INSTRUMENTS.md` is the guide for exactly that: where every instrument is defined in both files, recipes (swap a slice, change a default sound, add a control, add a new instrument, change the drums, swap one out), how to test with `tests/check_sound.py`, and the mistakes already made. Read it before changing any instrument.
- They did not say WHICH instruments. Ask what they want added or swapped, and whether a swap means "a different sound from the same video" or "a sample from my `drumnbasskit` folder" (its basses, subs, pads and one shots are unused). The second cuts across the source-first rule, so confirm it.
- Always tell them to restart `start.bat` FIRST after a change to `app.py` or `render.py`.

## What it is
A local tool for one user (Windows 10, Thorium browser). Paste a YouTube link; it downloads the video, slices the audio, builds a drill'n'bass / breakcore arrangement from the slices, and renders an MP4 where the picture is cut to the same edit list as the sound.

Run: `install.bat` once, then `start.bat`. The page opens at `http://localhost:5077`.

## The user
- Comfortable with computers, not an advanced programmer. Explain plainly. Prefers cmd over PowerShell.
- Works incrementally: one change, then they test. After each change say what changed, in which files, and how to test.
- Likes to see results as they are built. Send a screenshot when the UI changes.
- Any tool or site you mention needs a link you have actually checked.

## Rules learned the hard way (do not regress these)

### Look
Modern Swedish brutalism, kept quiet. The user rejected a dark "tracker" look and then a busier version of this one.
- THREE colours only per theme. Light (the default, unchanged): ground `#e4e2dc`, ink `#000`, highlight `#ffe500`. Dark (added 2026-11-16 at the user's request): the same two neutrals swapped, ground `#000`, ink `#e4e2dc`, highlight red `#d60000`. This replaces the old "no red" rule: red is allowed ONLY as the dark-mode highlight. No red in light mode, no yellow in dark mode.
- Errors are ink-coloured blocks with ground-coloured text (black on light, light on dark).
- The highlight (yellow / red) is for hover, the active/playing state, selection outlines and progress fill only. Same places in both themes.
- Theme switch: the small button at the right end of the status line (shows the theme it switches TO). It sets `data-theme="dark"` on `<html>`; the choice is kept in `localStorage` under `breakshredder-theme` and applied by a tiny script in `<head>` before the page draws. All colours come from the CSS variables `--ground`, `--ink`, `--hi`; never write a colour directly in a rule. `--screen` / `--screen-ink` are the fixed black and light used behind the video and thumbnails in both themes. Canvases (pad waveforms, bar drawings) are painted in the text colour, so the switch redraws the current page of pads and the bars. A dark theme is a colour change only: same layout, type and square corners.
- Type: Bahnschrift (ships with Windows 10), condensed and bold for big labels; a monospace only for the log.
- 4px black rules edge to edge between regions, 1px inside lists. No gaps between panels.
- No border-radius, no box-shadow, no gradients, no transitions, no emoji, no decorative numerals or placeholder panels.
- Slice classes are shown as words, not colours. Thumbnails are greyscale.
- The page opts out of the browser's forced dark mode and dark-mode extensions (`color-scheme: only light`, or `only dark` in its own dark theme; `darkreader-lock`). Keep that.
- Do not add clutter. If a panel is not built yet, it is not on the page.

### Performance
The first slice bank froze the browser on a 9 min 39 s video (1,506 slices).
- Never load the whole song into the page. Audio is fetched per slice (`/media/<id>/slice/<n>.wav`) and cached in `clips`.
- Never draw all pads. The bank shows `PAGE = 96` pads; the rest are paged.
- No per-element CSS filters on repeated elements.
- Test with a long source (9+ minutes, 1,500+ slices), not a 20 second clip.
- Pressing a button twice must not redo heavy work.

### The source supplies the music (user, 2026-11-16)
The original audio must supply most of the musical material. The tool makes a drum-and-bass song out of it by sampling, chopping, rearranging, pitching, stretching, looping, layering and effects.
- "Bass", "Reese", "Acid", drums and melodic parts are NAMES FOR HOW THE SOURCE IS PROCESSED. They must not automatically bring in separate synthesized instruments.
- Source sounds and processing are chosen automatically. The user must get a result without describing each instrument first.
- Extra synthesized sound is allowed only as an optional supplement. The default favours the source and keeps a recognisable link to it. (Later the same day the user asked for an optional ADDED DRUM KIT, synthesized is fine, with its own switch: see the current plan.)
- So: any new voice is built from slices first. An oscillator version, if there is one, goes behind the Synth switch (off by default).
- An instrument's own switch silences ALL of it. (Fixed 2026-11-21: oscillator copies used to check only the Synth switch, so with Synth on, unchecking Music box or Sub bass left the synthesized version playing; the user heard it as a sound "not from the video" that would not switch off.) Rule now, in `scheduleSynth` and the bar drawing (page) and the `for e in synth:` loop (`render.py`): a note is skipped if its voice is off, and an oscillator note also if Synth is off. `tests/check_sound.py`'s "SYNTH alone" row is therefore silent.

### Video effects
The user called the first effects (flash, zoom punch, RGB split, tear, colour shifts) "cheesy". They are switched off (`effects=False` in `render.render`). Renders are CLEAN CUTS: the picture only follows the edit (which slice, frame repeats, reverse, slow-down/speed-up). Do not turn the old effects back on. Later the user wants real artifact effects: dithering, pixelation, datamosh. Structure first, effects last.

### Preview and render must match
The page previews the arrangement; `render.py` exports it. Both read the same edit list, and every event in it is fully explicit (no randomness at playback). Any new sound must be implemented twice with the same maths: once in Web Audio (`scheduleEvent` / `voice` in `index.html`) and once in numpy (`render.py`). `rng32` (mulberry32) exists in both and must stay identical.

## Files
- `app.py` Flask server: tool detection (`bin`, PATH, `config.json`), ingest with yt-dlp, cache, media routes, analysis/render jobs.
- `analyze.py` librosa + FFmpeg analysis. Writes `cache/<id>/audio.wav`, `thumbs.jpg`, `analysis.json`.
- `render.py` offline export from an edit list to `renders/<name>.mp4|.wav|.edl.json|.log.txt` (which of mp4 / wav depends on the export type).
- `index.html` the whole page: CSS, markup and JS inline, one file. Keep it one file.
- `drumnbasskit/` the user's own drum sample pack, used by the Added drums kit (see stage 3).
- `INSTRUMENTS.md` how to add, change and swap instruments (for the next AI). `tests/check_sound.py` the sound check that goes with it.
- `config.json` port, `max_source_minutes`, `max_height`, `open_browser`, tool paths.
- `cache/<videoID>/` source.mp4, meta.json, audio.wav, thumbs.jpg, analysis.json, slices_user.json.

## Routes
`GET /api/status`, `GET /api/cache`, `POST /api/ingest`, `GET /api/job/<id>`,
`POST /api/analyze`, `GET /api/analyze/job/<id>`, `GET /api/analysis/<id>`, `POST /api/slices/<id>`,
`POST /api/render`, `GET /api/render/job/<id>`, `GET /renders/<name>`,
`GET /media/<id>/source.mp4|audio.wav|thumbs.jpg`, `GET /media/<id>/slice/<n>.wav`,
`GET /api/kit`, `GET /kit/<K|S|C|O>/<n>.wav`.

## Edit list (EDL) format
Built in `index.html` (`generate`, `genBar`), held in `eng.edl`, readable in the console as `BREAKSHREDDER.edl()`.

```
{ version: 1, video: "<id>", seed, bpm, intensity, ops: {ratchet, swap, displace, reverse, tail, stretch, stutter, meter},
  kit: { KICK: [slice numbers], SNARE: [...], HAT: [...], TONAL: [...], guessed: [...] },
  bars: [ { n, meter: "4/4", beats: 4, locked, regen, sec: "A", events: [ ... ] } ] }
```
Event (times in BEATS from the start of its bar, so BPM can change without regenerating):
```
{ t, d, s: slice number, role: KICK|SNARE|HAT|TONAL, g: gain 0..1, rate, rate2 (optional end rate, exponential ramp),
  rev (optional), op: HIT|RATCHET|STUTTER|STRETCH|REVERSE|TAIL, grain (ms, STRETCH), seed (STRETCH) }
```
Pitched voices live in each bar's `synth` list. Every note is written twice:
```
source note:     { t, d, voice: SUB|REESE|BOX|ACID, s: slice number, rate, rate0 (optional, slide from this rate), g, acc (optional accent) }
oscillator note: { t, d, voice, note (MIDI), from (optional slide), cents (optional), g, acc }      no "s"; silent unless Synth is on
```
`kit.src` = `{ SUB|REESE|ACID|BOX: { s, semis, g } }`: the slice each voice plays, how far it is transposed so its own note lands on the root, and its level. Muting: a source note follows its own voice switch (`mute.SUB` etc.); an oscillator note follows ONLY `mute.SYNTH` (true by default) and ignores the voice switches, so Synth works as one independent layer (the user expected to hear it with everything else off).
`mix` (top level of the edit list, added 2026-11-16) = `{ samples, instruments, master, SUB, REESE, BOX, ACID, SYNTH }`, each 0..150, 100 = as generated; gain = `(value/100)^2` (`level()` in both files). A missing `mix`, or a missing or unreadable value in it, counts as 100, so older edit lists render exactly as before (checked: identical WAV).
- Kick/snare/tonal events are monophonic: each lasts until the next one. They also drive the picture. Hats overlay and do not drive the picture.
- Each bar's seed is `barSeed(seed, n, regen)`. Regenerating a bar bumps `regen`.
- Song form (`FORM` in `index.html`): INTRO 2/16, BUILD 2/16, DROP A 4/16, INTERLUDE 2/16, DROP B 4/16, OUTRO 2/16 of the bars.

## Status against the original milestones
- M1 ingest, cache, playback: done, tested by the user.
- M2 analysis and slice bank: done, tested by the user. Class tags are rough (the test video gave 688 SNARE of 1,506).
- M3 break engine with live audio preview: done, user approved the sound.
- M4: song form done. Pitched voices SUB, REESE (DROP B), BOX (INTRO/INTERLUDE) and ACID (DROP B) done end to end (preview + render), now MADE FROM SOURCE SLICES by default, with the old oscillators behind the Synth switch. The user has NOT yet listened to any of the source-made voices, nor to the REESE, BOX or ACID oscillators. Mixer, sound panels with channel effects, and the added drum kit are done (stages 1, most of 2, and 3 of the current plan); stage 4 (export choices) is done too. ALL FOUR STAGES ARE BUILT; what is missing is the user's listening verdict on most of it (see "The stale-server trap"). Full timeline NOT done (there is a bar grid with per-bar regenerate and lock).
- M5 live video preview: NOT done. The picture only exists in renders.
- M6 advanced effects and mapping matrix: NOT done.
- M7 render: done as clean cuts at 1280x720, 30 fps, one pass. Peak-limited to -1 dBFS only; no LUFS targeting. fps/resolution not selectable.
- M8 presets, undo/redo, 1-9 pad keys, EDL load: NOT done (EDLs are saved beside each render but cannot be reloaded).

## CURRENT PLAN (user, 2026-11-16). This replaces the order of "Next steps" below where they differ.
Goal unchanged: turn the video's own audio into a drum-and-bass song. Source-made instruments stay central; the Synth layer stays optional and must keep doing what it does now. The user now also wants ADDED DRUMS and more control over the sound.
Work ONE STAGE AT A TIME. After each stage: say what changed, how to test it, then STOP so the user can listen before the next stage. Keep this file current.

Vocabulary the user set (groups are by MUSICAL ROLE, not by where the sound came from):
- **Samples** = the direct chopped video audio: KICK, SNARE, HAT, TONAL slice events with their existing processing.
- **Instruments** = source-made Sub bass, Reese, Music box, Acid + the optional Synth (oscillator) layer + the added drums of stage 3.
- **Master** = the complete mix.

**Stage 1, MIXER: DONE 2026-11-16, waiting for the user to listen.**
- Page: a row of eight sliders under the switches (`MIXER` list, `buildMixer`, `#mixer`): Samples, Instruments, Master, then Sub bass, Reese, Music box, Acid, Synth. 0..150, double-click a cell to reset to 100. The switch row is now labelled in two groups (Samples: Kick Snare Hat Tonal; Instruments: the rest); switches unchanged.
- Preview routing (`buildBus`, `applyMix`): slices -> `eng.bus.samples`; each pitched note -> `eng.bus[voice]` (an oscillator note -> `eng.bus.SYNTH`, matching the mute rule) -> `eng.bus.instruments`; both -> `eng.master` (gain `MASTER_TRIM` 0.8 x master level) -> compressor -> speakers. Sliders move the gains live (`setTargetAtTime`); nothing regenerates; `eng.mix` is the same object as `eng.edl.mix`.
- Render: the same gains are multiplied into each note's `g` when the bars are flattened, and the mix is multiplied by `MASTER_TRIM` x master BEFORE the peak check, so master cannot push past the -1 dBFS ceiling. The log has a `mixer:` line.
- Known, older difference: the preview's output protection is a compressor (it squashes loud moments), the export's is a whole-file turn-down to -1 dBFS. So a mix pushed hard sounds more squashed in preview than in the export. Fixing that properly belongs with the loudness step.
- Checked technically (not by ear): default mix and a mix-less edit list give a WAV identical to a render made before the mixer; Samples 50 scales exactly the slices by 0.25; Sub bass 150 scales exactly the sub by 2.25; Instruments scales all four; Synth scales only the oscillator notes; everything at 150 still peaks at -1 dBFS; master 0 is silence.

**Stage 2, SOUND CONTROLS PER INSTRUMENT: ALL THREE PARTS DONE 2026-11-16 (starter panels, channel effects, note options), waiting for the user to listen. Next in the user's order: stage 4, exports.**
What exists:
- Page: a "Sound" row under the mixer with one button per source-made instrument (`buildSound`, `paintSound`). A button opens that instrument's panel underneath (one open at a time; press again to close): a line saying what it shapes, Bypass, Reset, and a row of sliders. Double-click a slider's cell to reset that one control.
- Controls (`SND` table in `index.html`; the same limits and defaults in `SND` in `render.py`; DEFAULT = the sound before the panels existed):
  - Sub bass: Octave -2..+1 (0), Tune -12..+12 st (0), Cutoff 60..2000 Hz (200), Drive 0..100 (0), Length 10..100 % (100).
  - Reese: Detune 0..60 cents (14), Width 0..100 (0), Cutoff 100..8000 Hz (500), Distortion 0..100 (0).
  - Music box: Tune -24..+24 st (0), Attack 2..200 ms (2), Decay 10..100 % of the note (100), Brightness 300..16000 Hz (16000 = filter off), Reverb 0..100 (0).
  - Acid: Cutoff 80..2000 Hz (280), Resonance 0..24 dB per filter stage (8), Envelope 0..200 % (100), Decay 20..600 ms (160), Accent 0..200 % (100), Slide 0..200 ms (40).
- Saved in the edit list as `snd: { SUB: { on, oct, tune, cut, drive, len }, REESE: { on, det, width, cut, dist }, BOX: { on, tune, att, dec, bright, rev }, ACID: { on, cut, res, env, dec, acc, slide } }` in real units. `on: false` = bypassed (values kept, defaults used). `sound(voice)` in both files turns it into numbers: missing `snd`, bypass, or a missing / unreadable / out-of-range value gives the default, so older edit lists render identically (checked).
- Read AT PLAYBACK, never baked into notes: changing a control keeps notes and arrangement. In the preview a change is heard from the next notes scheduled (about a quarter second later); reverb amount changes at once.
- WHICH VERSION: the panels shape the SOURCE-MADE instrument only (notes with `s`). Oscillator notes of the Synth layer always use the defaults; the Synth switch and its mute rule are unchanged. The panel says so. If the user wants the Synth layer shaped too, give it its own panel rather than sharing these.
- Maths (both files): Drive/Distortion = `tanh(k x) / sqrt(k)`, `k = 1 + 24 (amount/100)^2`, after the filter and envelope, skipped at 0 (`driveCurve` / `drive`). Width = one detuned copy leans left, the other right (`near`/`far` gains). Acid accent scales the accent's extra filter opening and its extra loudness; resonance is level-compensated by `10^(-(res-8)/20)` (without it, 24 was about 8x louder). Reverb = convolution with seeded noise decaying 60 dB over `REVERB_SECONDS` 1.6 s, energy 1 (`impulse` / the `wet` block), wet gain `(amount/100)^2`, hung on the instrument's own mixer channel (`eng.inp[v]` -> send -> convolver -> `eng.bus[v]`) so it follows the mixer; the routing works for any instrument, only Music box has the slider so far.
- Known small differences preview vs export: the reverb noise is generated at the sound card's sample rate in the page and at 44100 in the export (same recipe and seed, so the same character, not the same samples when the card is not at 44.1 kHz); a reverb tail is cut at the end of an export; the Acid filter moves continuously in the page and every 64 samples in the export.
- Checked technically (not by ear): no `snd`, all defaults, and all-extreme-but-bypassed each give a WAV identical to a pre-panel render; every control at each end changes the export of its own instrument only (never the Synth layer), stays finite and keeps the song length; nonsense values do not break a render; in the page every control was run at both ends during playback with no errors, arrangement unchanged; Bypass, Reset and a render from the page carry the settings through (`reverb:` line in the log).
- Not verified: that preview and export sound the same for each control (no audio capture of the preview), and whether the ranges are musically right. Ask the user.

**Stage 2, second part DONE 2026-11-16 (channel effects on every source-made instrument), waiting for the user to listen.**
- Every panel now has a SECOND ROW, the same six controls for all four instruments (`SND_FX` in both files, appended to each instrument's table): Bits 4..16 (16 = off), Rate 500..44100 Hz (44100 = off), Delay 0..100 (0 = off), Time 1/16, 1/8, 3/16 or 1/4 note (saved as beats: 0.25, 0.5, 0.75, 1; default 0.75), Feedback 0..90 % (35), Reverb 0..100 (0). Music box's Reverb moved into this row; its saved key `rev` is unchanged. Saved keys: `bits, srate, dly, dtime, dfb, rev`.
- These sit on the instrument's whole CHANNEL, not on each note. Page: notes -> `eng.inp[v]` -> bits+rate (an AudioWorklet, code in `CRUSH_CODE`, loaded from a Blob; only inserted once an instrument uses it) -> `eng.post[v]` -> mixer level `eng.bus[v]`; delay (`createDelay` with a feedback gain) and reverb hang off `post` side by side and return into `eng.bus[v]`. All in `applySnd`, which is also called when BPM changes (delay time is in beats).
- Export: an instrument that uses any channel effect is collected into its own buffer (`chan` in `render.py`), then `crush()` -> echoes (a loop of delayed copies) and reverb -> multiplied by its mixer level -> mix. Instruments with no channel effect go straight to the mix as before.
- FIXED in this step: mixer levels used to be multiplied into a note's level BEFORE Drive/Distortion in the export but after them in the page, so with a mixer fader away from 100 the two distorted differently. The export now keeps the mixer level separate (`mg`) and applies it after all of an instrument's processing, like the page.
- Bits+rate maths: a clock at the reduced rate; on each tick take one sample, round it to the bit depth (`floor(x * 2^(bits-1) + 0.5) / 2^(bits-1)`), hold it until the next tick. Bits act on the signal before the mixer faders, so a quiet instrument crushes harder (as on real hardware).
- Known small differences preview vs export: the rate-reduction clock starts at a different moment (same character, not the same samples); echo and reverb tails are cut at the end of an export but ring on in the preview.
- Checked technically (not by ear): defaults / no `snd` / bypassed still give the identical pre-panel WAV; each effect changes only its own instrument; Delay 100 with no feedback is exactly the dry sound plus one copy an eighth note later; Rate 2000 holds values as expected; Time and Feedback do nothing while Delay is 0; a mixer fader at 50 gives exactly a quarter of the processed sound (drive, bits, delay, reverb); the worklet run on its own is bit-transparent when off and gives the same 9 levels as the export at 4 bits; in the page all controls were swept during playback with no errors and a render carried the settings (`effects ACID: ...` line in the log).

**Stage 2, third part DONE 2026-11-16 (note-level options, plus the missing resonance and distortion), waiting for the user to listen. With this, everything in the stage 2 brief has a control.**
- Panel layout for the four source-made instruments is now four rows (`SND_ROWS`): (1) the instrument's own sound, (2) Start, Reverse, Loop, Bend, Bend time, Stretch, (3) Retrig, Chance (and Acid's Distortion, which did not fit in its first row), (4) the effects row. Tables: own controls + `SND_NOTE` + `SND_EXTRA[v]` + `SND_FX`, the same in both files.
- New own-sound controls: Resonance 0..24 dB on Sub bass and Reese (`res`, level-compensated by `10^(-res/40)`); Distortion on Music box and Acid (`dist`, the same tanh curve, after the envelope).
- Note options (`SND_NOTE`; saved keys in brackets; all default to off), all inside `src()` in the page and `voiced()` in `render.py`:
  - Start (`pos`, 0..90 %): where in the slice each note begins.
  - Reverse (`back`, 0/1): the slice backwards. With Start 0 it begins at the slice's end.
  - Loop (`loop`, 0..200 ms, 0 = off): repeat only that much of the slice from the start point (`loopStart`/`loopEnd` in the page, a modulo in the export). Short loops become a buzzing tone whose pitch follows the note.
  - Bend (`bend`, -24..+24 st) and Bend time (`btime`, 5..500 ms): each note starts that far away and bends onto its pitch. A note that already slides from the previous note (Sub portamento, Acid slide) keeps its slide instead.
  - Stretch (`grain`, 0..120 ms, 0 = off): instead of looping the slice, crawl through it once per note in half-overlapping grains (64-point Hann window, grain k starts at `off + span * k / count`). Pitch and position are then separate. Loop is ignored while Stretch is on; Reverse uses the reversed slice.
  - Retrig (`rtg`, index 0..4 = Off, 1/4, 1/8, 1/16, 1/32 note; `RETRIG_STEPS` in beats) and Chance (`rchance`, 0..100 %): chops each longer note into repeats that restart the sound. THIS CHANGES TIMING, so it is not decided at playback: `applyRetrig()` in the page writes an explicit `rt` (step in beats) into each chosen source note of the edit list, after Generate, after Regenerate bar and whenever a sound control, Bypass or Reset changes. Which notes are chosen under Chance < 100 depends only on seed, bar and the note's index. `playNote` (page) and the flattening loop (`render.py`) expand a note with `rt` into pieces the same way; only the first piece keeps a slide. `render.py` never looks at `rtg`/`rchance`, only at `rt` in the notes.
- Source note format is now: `{ t, d, voice, s, rate, rate0?, g, acc?, rt? }`.
- Naming trap: the key `cut` means Cutoff on the instruments and "Cut picture" on the added drums; the key `rev` is Reverb, so Reverse is `back`.
- Checked technically (not by ear): no `snd`, all defaults, and everything-extreme-but-bypassed still give the identical pre-panel WAV; each new control changes only its own instrument's export; a retrigger step written into notes changes them and never the song length; Stretch, and all options at once, stay finite; a 10 ms loop gives a clear tone; in the page all new controls were swept during playback with no errors; Reset returns the edit list exactly to what it was; Retrig 1/16 on the bass marked 27 notes, Chance 50 marked 14, Bypass 0, and only `rt` differed from the original edit list; a render from the page completed.
- Things worth telling the user: Retrig on the bass can sound much quieter (each repeat restarts the slice at its quiet beginning; raise Start to fix); Stretch makes many small sound sources per note, so with Stretch on several instruments at once a slow machine might crackle in the preview (the export is unaffected).
- Not verified: preview against export by ear for any of these.

**ACID made bigger and crushed BY DEFAULT (2026-11-16, user: "the acid sounds weak. I want it to be a bigger more bit crushed sound. It just doesn't sound powerful enough").** This is the first real listening verdict on a source-made instrument.
- New Acid defaults (both files): Cutoff 360 Hz (was 280), Resonance 11 dB (8), Envelope 120 % (100), Decay 200 ms (160), Distortion 55 (0), new control Body 60 (a copy one octave below through the same filter; key `body`, third row), and on Acid's effects row Bits 6 and Rate 9000 Hz (were off; `ACID_FX_DEFAULTS` in the page, `SND["ACID"].update(...)` in `render.py` override the shared effects defaults for Acid only). Generation level `tuned(lead, 0, 0.3)` (was 0.25). `ACID_OUT` 1.9 multiplies the source-made acid after its distortion, because the distortion's own level compensation holds the peak down.
- Measured alone, loudest bar: acid was 0.082, is now 0.135 (sub bass 0.147, source slices 0.206). Without Distortion it drops to 0.059, so Distortion is doing most of the "power".
- CONSEQUENCE: Acid's default is no longer "the sound before the panels existed", so an Acid panel on Bypass, and older edit lists with no `snd`, now give the NEW acid. The other three instruments' defaults are unchanged.
- The Synth layer's oscillator acid is deliberately unchanged: `SND_OSC` (both files) pins its cutoff, resonance, envelope and decay to the old values, and it gets no distortion, body or output boost. Checked: a Synth-only render is identical to one from before.
- User's verdict on the new acid (2026-11-17): "good for now I guess. We'll change later". Accepted, not loved: expect to come back to it.
- If the user still finds it weak: raise Distortion and Body first, then lower Bits; the next structural step would be distortion BEFORE the filter (classic acid crunch) or longer notes.

Original brief for stage 2 (for the parts still to do): The source-made instruments sound too fixed; shape them like a normal synth while the source slice stays the starting sound. A compact, EXPANDABLE panel per instrument (no clutter), each with reset-to-default and bypass, restrained defaults, clearly audible controls. Start with:
- Sub bass: octave/tuning, filter cutoff, drive, note length.
- Reese: detune, stereo width, filter cutoff, distortion.
- Music box: tuning, attack/decay, brightness, reverb.
- Acid: cutoff, resonance, envelope amount, decay, accent, slide.
Then, incrementally, per instrument: retrigger/stutter/tiny loops; pitch envelopes and bends; distortion/saturation; bit depth and sample-rate reduction; resonant filtering; delay with controlled feedback; reverb; reverse, stretching and sample-start offset where appropriate.
Rules: changing a sound control keeps the notes and arrangement; timing changes such as retriggers must be saved explicitly in the edit list so preview and export agree; make clear which controls affect the source-made version and which the oscillator version; do not silently change what the Synth switch does. Most of today's fixed constants (`SUB_SRC_CUTOFF`, `REESE_CENTS`, `REESE_CUTOFF`, `ACID_*`, `BOX_*`, the octave in `kit.src[...].semis`) are the natural first controls: move them into a saved per-instrument settings object with those values as defaults.

**Stage 3, ADDED DRUMS: DONE 2026-11-16 (third pass), waiting for the user to listen.**
- HISTORY. Pass 1: a synthesized kit; the user said it "sounded horrible" and put their own sample pack in `drumnbasskit/`. Pass 2: the synthesized kit was REMOVED from both files (do not bring it back) and the kit plays their samples. Pass 3 (asked for all at once: "fix the pattern, use more of my kit, effects on the kit, drums cut the picture"): everything below. The user gave no detail on what was wrong with the pattern, so the fix was my judgement (see Pattern); ask what they think.
- WORKING ORDER the user set after a mix-up: finish the drums, THEN the rest of stage 2 (note-level options), THEN stage 4 exports. Stage 4 has NOT been started (only read). When offering "what next", do not let a button skip unfinished work: the user took "Stage 4 exports" to mean "after finishing what we are on".
- The kit folder `drumnbasskit/` (in the project folder; all files 44.1 kHz stereo float WAV): `kicks/kick N.wav` (30), `snares & claps/snare N.wav` (30) and `clap N.wav` (5), `hi hats/hat N.wav` (17) and `open hat N.wav` (6), `percs/perc N.wav` (42), `subs & basses/bass N.wav` (17) and `sub N.wav` (8), `pads and one shots/pad N.wav` (6) and `one shot N.wav` (6). Used: kick, snare, clap, hat, open hat, perc (`KIT_FILES` in `render.py`). NOT used: basses, subs, pads, one shots; ask before using them (they cut across the source-first rule).
- Drum letters in the edit list: K kick, S snare, L clap, C closed hat, O open hat, P and Q the two perc parts (both from the percs folder, different sample numbers).
- Switch "Added drums" at the end of the Instruments switches, OFF by default (`mute.DRUMS: true`). Mixer slider "Added drums" (`mix.DRUMS`), routed through Instruments. Sound row button "Added drums" opens its panel, four rows (`DRUM_ROWS`): (1) levels Kick, Snare, Clap, Closed hat, Open hat, Percs (0..150, mixer curve); (2) which sample: Kick, Snare, Clap, Hat, Open, Perc 1; (3) Perc 2 sample, Kick tune, Snare tune (-12..+12 st, by playing faster or slower), Drive 0..100, Cut picture On/Off; (4) the same effects row as the other instruments (Bits, Rate, Delay, Time, Feedback, Reverb). Saved as `snd.DRUMS = { on, kick, snare, clap, chat, ohat, perc, ksel, ssel, lsel, csel, osel, psel, qsel, ktune, sst, drv, cut, bits, srate, dly, dtime, dfb, rev }`. Sample choices default to 1 (Perc 2 to 2). Sample sliders stop at how many files the folder holds.
- Server (`app.py`): `GET /api/kit` gives the counts; `GET /kit/<letter>/<n>.wav` serves the file as it is on disk. `render.py` reads the same file with `soundfile`. `kit_path` and `kit_counts` in `render.py` are the one place that knows the folder layout.
- Sound, identical in page (`loadDrum`, `scheduleDrum`) and export (the added-drums block): the sample from its start, peak brought to 1 (so every sample is equally loud), times `DRUM_G` (K 0.7, S 0.6, L 0.4, C 0.25, O 0.2, P and Q 0.35), the hit's own `g`, the panel level and the mixer. A hit plays to the end of its sample, EXCEPT an open hat that has a length `d`: the next hat cuts it off with a 10 ms fade (`DRUM_CHOKE`). The length is written into the edit list at generation, so preview and export agree.
- Kit effects: the kit is one channel like the other instruments (`eng.inp.DRUMS` -> drive -> bits+rate -> `post` -> mixer level, delay and reverb off `post`). Drive is the same tanh curve as the instruments' but on the whole kit together (`drv`; `applySnd` rebuilds the chain when drive or bits+rate come into or out of use). Export: the kit goes through `emit` into `chan` whenever any of these is active, then `drive` -> `crush` -> echoes / reverb -> mixer level.
- Edit list: each bar has `drums: [ { t (beats), drum, g, s (optional: the source slice whose picture a kick or snare shows), d (optional: open hat length in beats) } ]`, always generated, whether or not the switch is on. Older edit lists without `drums`, or with drums without `s`, still work (no kit / no picture cuts).
- Pattern (`drumLine` in `genBar`). Backbone unchanged: kick on step 0 and 10, snare on 4 and 12 in EVERY drop bar, with a clap on each of those snares. THE FIX in pass 3: the groove around it used to be re-rolled every bar, which sounded restless. Now the groove (which kick variant, ghost snares at 7 / 9 / 15, open hats at 6 / 14, quiet 16th hats, up to three off-beat perc hits from steps 3, 7, 9, 11, 13, 15) is drawn from a stream seeded by SECTION and `n % 2` (`barSeed(seed, 500 + section*2 + n%2, 0) ^ 0x6A00D2D2`), so it repeats every two bars inside a section like a played loop; a regenerated bar gets its own. Only the fills are decided per bar (stream `^ 0xD2D2D2D2`): the last beat at the end of each drop and of half the four-bar phrases (roll of 32nds, four rising snares, or snare-kick-snare). BUILD: hats only, then a kick on 1 and quiet percs, and its last bar is a snare roll that speeds up and swells. OUTRO: full, then kick on 1 and snare on 2. INTRO, INTERLUDE and the final bar: nothing. It deliberately does NOT follow Intensity.
- PICTURE ("Cut picture", On by default; only matters while the kit is switched on): each added KICK and SNARE hit also cuts the video, to the picture of the source's own first kick slice (kicks) or snare slices (snares; fills flick through the snare slices). Stored per hit as `s`. In `render.py` these become extra picture events lasting until the next source cut; where a kit hit and a source slice land together the source slice is shown. Claps, hats and percs never cut the picture. With Cut picture Off, or the kit off, the video is exactly as before (checked frame by frame). There is still no live video preview in the page, so this is only visible in exports.
- Checked technically (not by ear or eye): kit off gives the pre-stage WAV exactly; same seed gives the same edit list; all six levels at 0 is silence; each sample choice, drive and effect changes the export; the mixer scales the processed kit exactly; cut-off open hats are shorter; in the page all seven samples load before Play and newly chosen ones at once, effects and drive were switched in and out during playback with no errors. Picture: with Cut picture Off 0 of 677 frames differ from kit-off; with it On 75 frames differ (80 kit cuts), drift still within one frame. Measured alone at default levels, loudest bar: kick 0.129, snare 0.088, clap 0.038, hats 0.02, percs 0.021; the whole kit 0.159 against the source slices' 0.206.
- Ideas not built: a different hat sample per hit; per-drum sample audition button; picture cuts for claps or percs; a slice chooser for what picture each drum shows.

Original brief for stage 3: An optional added kit (kick, snare, closed/open hat; synthesized is fine) to give a stronger drum-and-bass foundation. Separate from the source-sliced drums; the user must be able to blend the two or switch either off. Own switch and level, individual drum levels, a few sound controls; routed through Instruments. Groove first: solid kick/snare placement, variation, fills, occasional rolls; more hits is not better. Keep the source recognisable; the kit must not overpower it. Explain to the user what drives the picture when an added drum plays with no source slice.

**Stage 4, EXPORT CHOICES: DONE 2026-11-17, waiting for the user to try. With this, all four stages of the current plan are built.**
- Page: the old "Render MP4" button is replaced by an "Export" row of three buttons (class `exp`, `data-mode`): "Audio only: WAV", "Video only: silent MP4", "Audio + video: MP4" (this last one keeps the id `engRender` and the black look). All three are disabled while an export runs. The status line shows "<type> export N%" with the current step; the log gets "<type> export started." and "<type> export saved in the renders folder: <file> (plus ...)". The result is loaded into the preview screen (the WAV plays there with no picture).
- Server: `POST /api/render` takes `{ edl, mode }`, mode = `audio` | `video` | `both` (default `both`, so nothing older breaks). File names: `<video>_seed<n>_<date-time>` + `_audio` / `_video` / nothing. ffmpeg is only required for the two video modes.
- `render.render(..., mode="both")`: ONE code path. The sound is always worked out in full (the picture follows it); `audio` writes the WAV and returns before the picture; `video` writes no WAV and encodes the frames with `-an`; `both` muxes the WAV in. Every export writes `.edl.json` (the full edit list with `mix`, `snd`, `mute`, drums) and `.log.txt` (first line after the header says `export: ...`).
- FIXED here: the combined MP4 used `-shortest`, which dropped the last video frame whenever the sound ended inside it, so it was one frame shorter than the silent one. `-shortest` is gone; the picture is the song length rounded up to a whole frame in both.
- Checked: from the page, all three exports with mixer changes, Music box delay and reverb, and the added drums on: the audio-only WAV is byte-for-byte the WAV of the combined export; the silent MP4 has no sound track; silent and combined MP4 have the same 678 frames and every decoded frame is identical (937 MB compared); the three saved edit lists are identical and carry the settings; an unknown export type is refused with a clear message.
- Not checked by eye or ear: the exports themselves. Durations: WAV 22.59 s, both MP4s 22.6 s (the WAV is the exact song length; the picture rounds up to a whole frame).

Original brief for stage 4: Three labelled options: Audio only (WAV); Video only (silent MP4); Audio + video (MP4 with the finished mix). Same arrangement, duration and settings for all three; audio includes mixer, instrument settings and effects as heard; silent video keeps the same visual edit. Save the edit list beside each export. Clear progress and completion messages.

**Every stage:** preview and export aligned; generation deterministic and existing arrangements preserved; older saved settings get sensible defaults; long-source performance intact; report technical checks separately from sound quality only the user can judge.

## Next steps, in order (older list; the plan above takes priority)
0. **Listen to the source-made voices with the user and fix what is wrong** (choice of slice, tuning, levels, character). How they work:
   - `buildKit` in `index.html` fills `kit.src`. From the 12 best tonal/vocal slices (score = loudness x length x how un-percussive; locked slices first; at least 0.15 s long): the darkest (lowest centroid) is the bass and reese, the brightest the music box, the best of the rest the acid line. Locking a slice in the bank is how the user steers the choice.
   - Tuning: the analysis only knows each slice's note NAME (no octave), so a slice is shifted by at most 6 semitones to put its note on the root, plus a fixed octave per voice (bass -1, reese 0, acid 0, box +1). Real pitch tracking in `analyze.py` (e.g. librosa pyin) would make this far more accurate; it needs a re-analysis.
   - Level: `g` = a per-voice factor (the numbers in the `tuned(...)` calls) x drum loudness / slice loudness, limited to 0.25..8. On the test video one render measured, per voice alone: drums 0.165 rms, bass 0.118, reese 0.068, acid 0.065, box 0.036.
   - `layer()` in `genBar` turns each oscillator note into a source note (`rate` from `kit.src[voice].semis` and the note's distance from the voice's base note, `SRC_BASE`).
   - Sound: the slice replaces the oscillator and runs through the SAME filters and envelopes (`scheduleSynth` / the pitched-voices loop in `render.py`). It is looped forwards-then-backwards (`pingPong` in the page, `looped` in `render.py`) so it never runs out and has no jump at the loop points. The bass adds a lowpass at `SUB_SRC_CUTOFF`.
   - Ideas not built yet, all from source: a different slice per section; several slices per voice; stretching (grains) for long bass notes instead of looping; melodic lines that follow the source's own note order.
1. **Rest of the pitched layer.** SUB is the worked example; copy its pattern for each new voice, source version first:
   - Data: each bar has `synth: [ { t, d, voice: "SUB", note (MIDI number), from (optional previous note, means slide in), g } ]`, times in beats. `kit.root` is the root note (most common note among the tonal slices, placed in the sub octave).
   - Generation: `subLine(bar)` inside `genBar` in `index.html`. It uses its own random stream (`barSeed(...) ^ 0x5B5B5B5B`) so toggling a voice never changes the drums. Give each new voice its own XOR constant.
   - Preview: `scheduleSynth` in `index.html` (OscillatorNode + gain envelope), called from `tick`.
   - Render: the "synth voices" loop in `render.py`. Constants `SUB_GLIDE`, `SUB_ATTACK`, `SUB_RELEASE`, `SUB_OCTAVE_MIX` exist in BOTH files and must match.
   - UI: the Instruments row has one on/off switch per instrument (`INSTRUMENTS` list: KICK, SNARE, HAT, TONAL, SUB). Switches MUTE at playback (`eng.mute`, saved in the EDL as `mute`, respected by `render.py`); they never regenerate, so the arrangement is unchanged. Add each new voice to `INSTRUMENTS`. Muted roles also stop driving the picture. Notes draw as a strip along the bottom of each bar cell.
   - REESE (`reeseLine`, follows the sub one octave up) and BOX (`boxLine`, own stream `^ 0x0B0B0B0B`, detune in `cents`) were added the same way. First ask the user how they sound and fix levels (`g` in each line function).
   - ACID (`acidLine`, own stream `^ 0xAC1DAC1D`, DROP B only) was added on 2026-11-16: a 16th-note riff two octaves above `kit.root`, repeating every two bars (seeded with `n % 2`; a regenerated bar gets its own). Events carry `acc: true` (accent: louder `g`, filter peak x `ACID_ACCENT`) and `from` (slide in from that note; the note before is lengthened to touch it). Sound: one saw into two lowpass filters in a row (24 dB/octave, `ACID_Q` dB of resonance each), cutoff falling exponentially from `ACID_PEAK` to `ACID_BASE` over `ACID_DECAY` on every note. The page moves the cutoff continuously; `render.py` updates it every `ACID_BLOCK` = 64 samples, carrying the filter state across blocks. `ACID_*` constants exist in both files. Levels are a guess (`g` 0.14, accent 0.2): ask the user.
   - With SUB + REESE + ACID together, DROP B pushed the test render to +3.3 dBFS before limiting, so the peak limiter turns the WHOLE render down about 4 dB. Balance the voice levels with the user, and see step 3.
   - Added drums: see stage 3 of the current plan (the user now wants an optional added kit with its own switch, not behind the Synth switch).
2. **Filtered build**: lowpass on the break during BUILD, opening over the section. Needs the same filter in preview (BiquadFilter) and render (scipy is installed).
3. **Loudness**: measure with FFmpeg's `ebur128`/`loudnorm` (no new install) and bring renders to about -9 to -7 LUFS, true peak at or under -1 dBTP.
4. **EDL load**, then presets (parameter sets only), undo/redo, 1-9 pad keys.
5. **Live video preview** in the page, following the same events as the render.
6. **Render options**: fps 30/60, resolution, repeat count.
7. **Real artifact effects** (dither, pixelation, datamosh) and the mapping matrix. Ask the user to confirm the look of each before building it.

## The stale-server trap (happened 2026-11-16; read this)
The user kept ONE `start.bat` window open from 04:58 to past 13:27 while `app.py` and `render.py` were changed many times. A running server keeps the old copies in memory, but `index.html` is read fresh on every refresh. Result: the page asked for `/api/kit` and `/kit/...` and the old server answered 404 to every one, so the added drums were completely SILENT for the user, and every export they made in that time used the OLD renderer (no mixer, no sound panels, no drums). They reasonably thought the drums were broken. They were not: the code was complete and passed on a fresh server. "Restart start.bat" had been in every test instruction, as one line among several; that was not enough.
- Consequence for what the user has actually judged: they have NEVER HEARD the sample kit, the kit pattern rework, claps/percs, or kit effects; and no export they listened to before restarting included the mixer or sound controls. Their only drum verdict ("horrible") was for the synthesized kit, which played without the server. Treat stages 1 to 3 as unheard in exports.
- Guard added: `app.py` records the modification times of `app.py`, `render.py`, `analyze.py` at start (`STARTED_WITH`); `/api/status` returns `stale: [files changed since]`; the page then logs an error block and sets the status line to "Restart needed - see log". The added drums' sample list also logs a clear restart message if `/api/kit` is missing. The status check only runs when the page loads, so the user must still refresh.
- When reporting a change that touches `app.py` or `render.py`, put the restart FIRST and on its own, not inside a numbered test list.

## How it was tested
`.claude/launch.json` starts a second copy of the server on port 5079 without opening the user's browser, for the Claude desktop app's browser pane. The user often has `start.bat` running on 5077 at the same time; leave that one alone. A running server keeps the OLD `render.py` and `app.py` in memory: after changing it, the user must close the black window and run `start.bat` again (the page itself only needs a refresh).
Headless Chrome via Playwright against the running server, with a synthetic clip in `cache/`, checking for console errors, that the same seed gives an identical edit list, and that a render completes. Nobody but the user can judge how it sounds or looks; say so when reporting.
