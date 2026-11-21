I'll write this as a build prompt for an AI coding assistant. First I'm checking the links for the core tools it depends on.

**Fidelity:** close stylistic adaptation. The prompt describes the production techniques behind Aphex Twin and Venetian Snares, not their actual tracks or likenesses. **Target:** Claude (or any strong coding assistant) building a local project. A small local server is required because a browser page can't pull YouTube media on its own.

```
ROLE
You are a senior creative-coding engineer who is also a breakcore / drill'n'bass producer and a glitch-video artist. You are building a personal local tool for one user on Windows 10 (browser: Thorium, Chromium-based). The user is comfortable with computers but is not an advanced programmer: explain setup steps plainly and keep the install to a few commands.

PROJECT: "BREAKSHREDDER" (working name)
The user pastes a YouTube URL. The tool downloads the video, analyzes it, and turns BOTH the audio and the picture into one new audiovisual piece in the style of 1990s–2000s drill'n'bass / breakcore. Techniques to reach for: hyper-edited Amen-style break programming, ratcheting snare rolls, odd meters, pitch-bent break tails, detuned melodic interludes, and sudden whiplash between beauty and violence. The video is edited frame-accurately to the same edit list as the audio, so every audio slice, stutter, reverse and pitch move has a matching visual event. The result should feel authored and deliberate, not random noise.

────────────────────────────────
1. ARCHITECTURE (do not deviate without asking)
- Backend: Python 3 + Flask on localhost (port 5077). Responsibilities: fetch, decode, analysis, offline render/export.
  - Fetch: yt-dlp (https://github.com/yt-dlp/yt-dlp), called as a subprocess. YouTube extraction in current yt-dlp may need a JavaScript runtime such as Deno. Detect this and show a clear message if it's missing.
  - Media: FFmpeg (https://ffmpeg.org/download.html). Portable-tool detection: look in ./bin first, then PATH, then a user-set path in config.json. Never hard-fail silently.
  - Analysis: librosa (https://librosa.org/doc/latest/index.html). Use HPSS to separate harmonic and percussive parts, onset_strength / onset_detect with backtracking for slice points, beat_track for the source tempo, spectral centroid and RMS per slice, and chroma per slice for pitched material.
  - Video analysis via FFmpeg: scene-cut detection (select='gt(scene,0.3)'), keyframe positions, and per-slice average luma and motion energy.
- Frontend: ONE self-contained index.html served by Flask (all CSS/JS inline). Uses the Web Audio API for real-time preview, plus WebGL2 for real-time video FX preview drawn from a <video> element texture.
- Render: the frontend's arrangement is serialized as a JSON "EDIT DECISION LIST" (EDL). The backend renders the final file offline from the EDL (audio with numpy/scipy, video with FFmpeg filtergraphs and/or frame-by-frame numpy processing). Preview and render must come from the same EDL, so what you hear and see is what you export.
- Output: MP4 (H.264 -preset veryfast, CRF 18, yuv420p) + AAC 320k, plus a WAV stem, plus the EDL JSON saved next to it so a render can be reloaded and re-edited.
- File layout: C:\Tools\_new\breakshredder\ (app.py, index.html, config.json, bin\, cache\<videoID>\, renders\).
- Cache everything per video ID: source file, analysis JSON, slice thumbnails. Re-opening a URL must be instant.

2. PIPELINE
 a. INGEST: paste URL → validate → yt-dlp best video ≤1080p + best audio → remux to cache. Show progress by parsing yt-dlp output. Optional in/out trim before analysis.
 b. ANALYZE: produce analysis.json with: source BPM, onset list (time, strength, percussive/harmonic class), slice list (start, end, RMS, centroid, chroma peak, class tag KICK-LIKE / SNARE-LIKE / HAT-LIKE / TONAL / NOISE / VOCAL-ish by simple feature heuristics), scene cuts, and per-slice video motion and luma.
 c. SLICE BANK: every slice becomes a pad: audio waveform + a filmstrip thumbnail, color-coded by class tag. The user can audition, delete, lock, or re-tag slices.
 d. GENERATE: an arrangement engine (section 3) writes an EDL at a target BPM.
 e. PERFORM / EDIT: a timeline grid where the user can regenerate one bar, lock bars, draw ratchets, and paint FX lanes.
 f. RENDER: offline, deterministic (seeded RNG; the seed is shown in the UI and stored in the EDL).

3. AUDIO ENGINE: THE MUSICAL DNA
Target tempo is 160–260 BPM (default 174, a "VENETIAN" preset at 200+). Grid resolution is down to 1/64, with triplet and quintuplet subdivisions.

Break programming (the core):
- Build "break kits" from the source's percussive-class slices. If the source has no usable drums, synthesize a drum kit (see Synthesis), and tonal slices still get chopped as melodic/texture material.
- Pattern grammar, not randomness: start from a 2-bar backbone (kick on 1 and the "and" of 2, snare on 2 and 4 at half-time feel, i.e. the classic jungle shuffle), then apply MUTATION OPERATORS per bar with tunable probabilities:
  • RATCHET: retrigger one slice at 1/16 → 1/32 → 1/64 with rising or falling pitch (the machine-gun snare roll), with an optional exponential accel/decel curve.
  • SHUFFLE-SWAP: replace a hit with a different slice of the same class.
  • DISPLACE: shift a hit by ±1/32 or ±1/48 for lurching, off-grid swing.
  • REVERSE: reverse a slice, usually the slice before a downbeat.
  • PITCH-TAIL: the last 1/8 of a phrase pitch-drops (tape-stop) or pitch-rises ±24 st over the tail.
  • STRETCH: granular time-stretch of a single hit into a smeared pad (grain 20–80 ms, Hann window, jitter).
  • GATE-STUTTER: repeat a 1/32 window N times with decreasing volume.
  • METER BREAK: allow bars in 7/8, 5/4, 7/4 or 11/8 within an otherwise 4/4 track (drill'n'bass odd-meter whiplash). Selectable per section.
- Density curve: each section has an intensity value 0–1 that scales mutation probability, ratchet depth and FX amount.

Song form (auto-arranged, editable):
INTRO (tonal slices, stretched, detuned, sparse: a fragile "ambient" opening) → BUILD (break enters filtered) → DROP A (full break carnage) → INTERLUDE (sudden near-silence or a soft melodic passage with music-box-like detuned tones from chroma-matched slices) → DROP B (heavier, odd meters, maximum ratchets) → OUTRO (collapse: everything pitch-tails and time-stretches into a drone, or a hard cut to silence). Hard, unannounced transitions are a feature, not a bug.

Synthesis layer (the musical glue, generated in-engine):
- SUB: sine/triangle sub-bass following root notes derived from the source's chroma, with portamento.
- ACID-ish mono line: saw/square → resonant 24 dB lowpass with envelope modulation, accent and slide (303-style behaviour, not a sample).
- REESE: two detuned saws through lowpass, slow detune modulation.
- Optional synthesized drum kit (sine-sweep kick, noise+tone snare, filtered noise hats) used to back up or replace weak source drums.
- Detuned pad / "music box" voice for interludes: slight random pitch drift ±15 cents, soft bitcrush.

Mangling FX (per-slice and per-bus, automatable on FX lanes):
bitcrush (bit depth + sample-rate reduction), waveshaper/saturation, ring mod, comb filter, resonant filter sweeps, granular freeze, tape-stop, buffer repeat, short metallic reverb, ping-pong delay synced to the grid, and a master glue compressor + brickwall limiter with a −1 dBTP ceiling. Heavy but never clipping the export.

4. VIDEO ENGINE: SAME EDL, MATCHING EVENTS
Every audio event in the EDL carries a video instruction. Default mappings (all user-remappable in a mapping matrix):
- SLICE PLAYBACK → show the video frames from that slice's source time (true audiovisual sampling: you see the moment you hear).
- RATCHET → frame-repeat stutter at the same rate, with a slight zoom step per repeat.
- REVERSE → reversed frames.
- PITCH-TAIL down → slow-motion with frame blending + colour drain; up → speed-ramp + hue rotation.
- STRETCH / granular freeze → frame freeze with slit-scan or time-displacement smear (each row of pixels from a different time offset).
- KICK-class hits → luma flash / zoom punch-in (2–4 frames, eased).
- SNARE-class hits → hard RGB channel split (offset proportional to hit strength).
- HAT-class hits → scanline jitter / horizontal tear.
- BITCRUSH amount → pixelation block size + palette reduction with ordered (Bayer) dithering.
- DATAMOSH sections → real datamosh: remove I-frames from a re-encoded segment so motion vectors bleed one shot into the next (P-frame bloom). Do this with FFmpeg + a byte-level I-frame drop on an AVI/Xvid intermediate, then re-encode. Also offer a cheaper "fake mosh" WebGL shader (optical-flow-ish displacement feedback) for live preview.
- METER BREAK bars → mirror / kaleidoscope tiling, hard-cut between tile counts.
- INTERLUDE → near-monochrome, heavy grain, slow-scan, CRT phosphor glow, soft vignette-free framing.
- DROP B → everything allowed at once, but the EDL intensity value must still govern it so it builds rather than staying flat.
Extra visual FX bank: pixel sorting (luma-threshold sorted runs), feedback zoom tunnel, edge-detect + posterize, ASCII render (monospace glyph ramp), VHS chroma bleed, interlace comb, frame-diff "ghost" trails. Every FX has an amount 0–1 and can be drawn on an FX lane.
Visual timing must be frame-accurate to the audio at the output frame rate (default 30 fps; offer 60). Snap audio events to the nearest frame boundary and report max drift in the render log.

5. UI DESIGN — HARD CONSTRAINTS
This is a dense instrument, not a SaaS page. Aesthetic direction: late-90s tracker / hardware-sampler front panel crossed with an exposed engineering grid.
- BANNED: border-radius anywhere, box-shadow, glassmorphism / backdrop-blur, decorative or purple/indigo gradients, gradient text, Inter / system-ui / generic sans stacks, emoji as icons, centered-card-on-shadow layouts, even "safe" padding rhythm.
- USE: monospace or bitmap-style type (e.g. a pixel/terminal font loaded locally or a mono stack like "IBM Plex Mono", "JetBrains Mono", monospace), a visible 1px grid, hard-edged rectangles, asymmetrical layout (big preview screen top-left, slice bank as a dense tracker-style matrix, timeline full-width bottom, parameter strip on the right), a near-black background with 1 harsh accent colour + 1 warning colour, and tiny uppercase labels. Pads and steps are raw squares.
- Layout regions: [URL BAR + status log] / [PREVIEW SCREEN with live WebGL FX] / [SLICE BANK MATRIX] / [ARRANGEMENT TIMELINE with per-bar regenerate/lock + audio lanes + FX lanes] / [MUTATION + FX PARAMETER STRIP] / [MAPPING MATRIX audio-event → video-FX] / [RENDER panel with seed, BPM, fps, resolution, progress].
- Keyboard: space play/stop, R regenerate selected bar, L lock, 1–9 audition pads, Ctrl+Z/Y undo/redo of EDL edits.
Before writing any UI code, restate in 4–6 lines which specific visual elements you will use (font, colours, grid, layout regions) so the user can correct drift before work begins.

6. PRESETS (each is a parameter set, not a hard-coded song)
- "AMEN SURGERY": 174 BPM, 4/4, heavy ratchets, classic jungle shuffle backbone, moderate video glitch.
- "VENETIAN": 200–240 BPM, frequent 7/4 and 7/8 bars, extreme snare rolls, rapid melodic interludes, maximal RGB split + stutter.
- "RICHARD'S GARDEN": 160–180 BPM, ambient detuned intro/interludes, acid line, glitchy but pretty, slit-scan and slow datamosh.
- "PULVERIZE": breakcore/noise extreme, gabber-ish distorted kicks, datamosh everywhere, pixel sort, ASCII.
- "SURGICAL": restrained, tight, minimal visual FX: proof that the edit itself carries the piece.

7. BUILD ORDER — incremental, one milestone at a time, stop and let the user test after each
M1: Flask server + tool detection + URL ingest + cache + playback of the raw source in the page.
M2: Analysis + slice bank (audition pads with filmstrip thumbnails).
M3: Break engine (backbone + mutation operators) with live Web Audio preview, audio only.
M4: Synthesis layer + song-form arranger + timeline.
M5: Video slice playback synced to audio in preview + core FX (stutter, RGB split, flash, reverse).
M6: Advanced FX (datamosh, slit-scan, pixel sort, ASCII, feedback) + mapping matrix.
M7: Offline deterministic render to MP4/WAV/EDL + render log with drift report.
M8: Presets, undo/redo, keyboard shortcuts, EDL save/load.
After each milestone, state plainly what changed, which files, and how to test it.

8. QUALITY BARS
- The output should groove: ratchets land on the grid, odd-meter bars resolve back to the downbeat, transitions are hard and intentional.
- No DC offset or clicks at slice boundaries (2–5 ms fades unless "hard cut" is intended).
- Loudness: integrated about −9 to −7 LUFS, true peak ≤ −1 dBTP.
- Deterministic: same URL + EDL + seed = identical output.
- Errors (age-restricted video, missing FFmpeg/Deno, too-long source) show human-readable messages in the status log, never a stack trace in the UI.
- Source limit default 15 minutes, analysis downsampled where safe, video analysis at reduced resolution for speed.
- For personal, experimental use. Note in the README that output from copyrighted sources is for private use.
```

**Settings and notes**
- **Best engine:** Claude, working as a full local project with file and computer tools. Paste this as the first message. The milestone order lets you see it working after each step instead of getting one giant drop.
- The point that's easiest to get wrong is that preview and final render share one edit list. That's what keeps the audio and video locked together instead of drifting apart. If a build cuts corners, push back on that first.
- The real datamosh (milestone M6) is the riskiest piece. If it stalls, the shader-based "fake mosh" is a fallback that's already in the prompt.

**Links**
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) handles the download. Current builds will soon require users to install a JavaScript runtime like Deno, so the prompt has the tool check for one.
- [FFmpeg](https://ffmpeg.org/download.html): FFmpeg only provides source code officially; executable binaries are distributed by third-party build maintainers. That download page links to Windows builds like [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
- [librosa](https://librosa.org/doc/latest/index.html) does the beat and onset detection. Its submodules include librosa.beat — Functions for estimating tempo and detecting beat events.

I couldn't open these sites directly from here. I confirmed them through search results, and the gyan.dev link is the main Windows build source referenced from FFmpeg's download page.

Do you want to start building this in a new chat? It fits a **full local project**: a Python server plus a page, saved to `C:\Tools\_new\breakshredder`. A single artifact won't work because it can't fetch YouTube.