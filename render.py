"""
BREAKSHREDDER - offline render

Reads an EDIT DECISION LIST (the same one the page previews) and writes:
  renders/<name>.mp4       picture + sound
  renders/<name>.wav       sound only
  renders/<name>.edl.json  the edit list, so the render can be reloaded later
  renders/<name>.log.txt   what was done, including picture/sound drift

Nothing here is random: the same video + edit list always gives the same files.
The audio maths mirrors the page's live preview (same fades, same pitch ramps,
same grain positions), so the export matches what was heard.
"""

import json
import math
import subprocess
import time
import wave
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SR = 44100
MAX_SLICE_VIDEO = 2.0      # seconds of picture kept per slice (slices are short)
SUB_GLIDE, SUB_ATTACK, SUB_RELEASE, SUB_OCTAVE_MIX = 0.06, 0.005, 0.03, 0.3   # must match index.html
BOX_ATTACK, BOX_THIRD_MIX, BOX_FLOOR = 0.002, 0.25, 0.01                       # must match index.html
REESE_CENTS, REESE_CUTOFF, REESE_ATTACK, REESE_RELEASE = 14, 500.0, 0.01, 0.04  # must match index.html
ACID_BASE, ACID_PEAK, ACID_ACCENT, ACID_DECAY, ACID_Q = 280.0, 2200.0, 2.0, 0.16, 8.0   # must match index.html
ACID_GLIDE, ACID_ATTACK, ACID_RELEASE = 0.04, 0.003, 0.012                              # must match index.html
SUB_SRC_CUTOFF = 200.0                                                                 # must match index.html
REVERB_SECONDS, REVERB_SEED = 1.6, 0x2E7E2B                                            # must match index.html
# Sound panels: per source-made instrument, key -> (lowest, highest, default). Must match SND in index.html.
SND = {
    "SUB":   {"oct": (-2, 1, 0), "tune": (-12, 12, 0), "cut": (60, 2000, 200), "res": (0, 24, 0), "drive": (0, 100, 0), "len": (10, 100, 100)},
    "REESE": {"det": (0, 60, 14), "width": (0, 100, 0), "cut": (100, 8000, 500), "res": (0, 24, 0), "dist": (0, 100, 0)},
    "BOX":   {"tune": (-24, 24, 0), "att": (2, 200, 2), "dec": (10, 100, 100), "bright": (300, 16000, 16000), "dist": (0, 100, 0)},
    "ACID":  {"cut": (80, 2000, 360), "res": (0, 24, 11), "env": (0, 200, 120), "dec": (20, 600, 200), "acc": (0, 200, 100),
              "slide": (0, 200, 40), "dist": (0, 100, 55), "body": (0, 100, 60)},
}
# What every source-made instrument can do to each note (SND_NOTE in index.html). All default to off.
SND_NOTE = {"pos": (0, 90, 0), "back": (0, 1, 0), "loop": (0, 200, 0), "bend": (-24, 24, 0), "btime": (5, 500, 60),
            "grain": (0, 120, 0), "rtg": (0, 4, 0), "rchance": (0, 100, 100)}
# Effects every source-made instrument has (SND_FX in index.html). All default to off.
SND_FX = {"bits": (4, 16, 16), "srate": (500, 44100, 44100), "dly": (0, 100, 0), "dtime": (0.25, 1, 0.75), "dfb": (0, 90, 35),
          "rev": (0, 100, 0)}
for _table in SND.values():
    _table.update(SND_NOTE)
    _table.update(SND_FX)
# ACID is big and crushed out of the box (the user found the plain version weak): its own defaults for the channel's
# Bits and Rate. SND_OSC keeps the Synth layer's oscillator acid exactly as it was. Both must match index.html.
SND["ACID"].update({"bits": (4, 16, 6), "srate": (500, 44100, 9000)})
SND_OSC = {"ACID": {"cut": 280, "res": 8, "env": 100, "dec": 160}}
ACID_OUT = 1.9             # the source-made acid's level after its distortion; must match index.html
# Added drum kit (no channel effects, so it is added after the loop above). Must match SND.DRUMS in index.html.
SND["DRUMS"] = {"kick": (0, 150, 100), "snare": (0, 150, 100), "clap": (0, 150, 100), "chat": (0, 150, 100), "ohat": (0, 150, 100),
                "perc": (0, 150, 100),
                "ksel": (1, 99, 1), "ssel": (1, 99, 1), "lsel": (1, 99, 1), "csel": (1, 99, 1), "osel": (1, 99, 1), "psel": (1, 99, 1),
                "qsel": (1, 99, 2), "ktune": (-12, 12, 0), "sst": (-12, 12, 0), "drv": (0, 100, 0), "cut": (0, 1, 1)}
SND["DRUMS"].update(SND_FX)
# The kit is the user's own samples: <this folder>/drumnbasskit/<folder>/<name> <number>.wav
# Drum letters: K kick, S snare, L clap, C closed hat, O open hat, P and Q the two perc parts.
KIT_DIR = Path(__file__).resolve().parent / "drumnbasskit"
KIT_FILES = {"K": ("kicks", "kick"), "S": ("snares & claps", "snare"), "L": ("snares & claps", "clap"), "C": ("hi hats", "hat"),
             "O": ("hi hats", "open hat"), "P": ("percs", "perc"), "Q": ("percs", "perc")}
DRUM_PICK = {"K": "ksel", "S": "ssel", "L": "lsel", "C": "csel", "O": "osel", "P": "psel", "Q": "qsel"}
DRUM_LEVEL = {"K": "kick", "S": "snare", "L": "clap", "C": "chat", "O": "ohat", "P": "perc", "Q": "perc"}
DRUM_G = {"K": 0.7, "S": 0.6, "L": 0.4, "C": 0.25, "O": 0.2, "P": 0.35, "Q": 0.35}   # must match index.html
DRUM_CHOKE = 0.01          # an open hat cut off by the next hat fades out over this long; must match index.html


def kit_path(drum, number):
    """The file for sample 'number' (1, 2, 3...) of a drum, or None if there is no such file."""
    if drum not in KIT_FILES:
        return None
    folder, stem = KIT_FILES[drum]
    path = KIT_DIR / folder / f"{stem} {int(number)}.wav"
    return path if path.is_file() else None


def kit_counts():
    """How many consecutively numbered samples each drum has."""
    counts = {}
    for drum in KIT_FILES:
        n = 0
        while kit_path(drum, n + 1):
            n += 1
        counts[drum] = n
    return counts


MASTER_TRIM = 0.8                                                                      # must match index.html
ACID_BLOCK = 64            # the filter cutoff is updated every 64 samples (1.5 ms); the page moves it continuously


class RenderError(Exception):
    """An error with a message that is safe to show in the page."""


def rng32(seed):
    """Same generator as the page (mulberry32), so grains land in the same places."""
    state = [seed & 0xFFFFFFFF]

    def imul(x, y):
        return (x * y) & 0xFFFFFFFF

    def nxt():
        state[0] = (state[0] + 0x6D2B79F5) & 0xFFFFFFFF
        a = state[0]
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return nxt


def level(p):
    """Mixer value (0..150, 100 = unchanged) to a gain. Same curve as level() in the page.
    Missing or unreadable values count as 100, so edit lists saved before the mixer existed sound as they did."""
    try:
        p = 100.0 if p is None else float(p)
    except (TypeError, ValueError):
        p = 100.0
    if p != p:
        p = 100.0
    p = max(0.0, min(150.0, p))
    return p * p / 10000.0


def sound(snd, voice, plain=False):
    """One instrument's sound settings as plain numbers. Same rules as sound() in the page: a missing "snd" (older
    edit lists), a bypassed panel (on: false), or a missing / unreadable / out-of-range value gives the default."""
    saved = snd.get(voice) if isinstance(snd, dict) else None
    use = not plain and isinstance(saved, dict) and saved.get("on") is not False
    out = {}
    for key, (lo, hi, default) in SND[voice].items():
        value = default
        if use:
            try:
                value = float(saved.get(key, default))
            except (TypeError, ValueError):
                value = default
            if value != value:
                value = default
        out[key] = max(lo, min(hi, value))
    if plain:                                     # the Synth layer's oscillator: its own fixed values
        out.update(SND_OSC.get(voice, {}))
    return out


def source_offset(local, dur, rate, rate2):
    """How far into the slice (seconds) playback has got, 'local' seconds after the event began."""
    if rate2 and abs(rate2 - rate) > 1e-9:
        k = rate2 / rate
        return rate * dur / math.log(k) * (k ** (local / dur) - 1.0)
    return local * rate


EXPORT_MODES = {"audio": "audio only (WAV)", "video": "video only (silent MP4)", "both": "audio + video (MP4)"}


def render(edl, analysis, cache_dir, renders_dir, ffmpeg, name, progress, fps=30, width=1280, height=720, effects=False,
           mode="both"):
    # mode: "audio" writes <name>.wav; "video" writes a silent <name>.mp4; "both" writes <name>.mp4 with the mix (and the
    # .wav it was made from). All three run the SAME code on the same edit list: the sound is always worked out in full
    # (the picture follows it), and only what gets written differs. Every export also saves .edl.json and .log.txt.
    if mode not in EXPORT_MODES:
        raise RenderError("Unknown export type.")
    # effects=False means CLEAN CUTS: the picture only follows the edit (which slice, repeats, reverse,
    # slow-down/speed-up). The flash / RGB split / tear effects below stay in the file, switched off,
    # until the real artifact effects (dither, pixelation, datamosh) are built.
    try:
        import numpy as np
    except ImportError:
        raise RenderError("Rendering needs numpy. Run install.bat again, then retry.")

    cache_dir, renders_dir = Path(cache_dir), Path(renders_dir)
    renders_dir.mkdir(exist_ok=True)
    slices = analysis["slices"]
    bpm = float(edl.get("bpm") or 174)
    if not 40 <= bpm <= 400:
        raise RenderError("BPM is out of range.")
    spb = 60.0 / bpm
    log_lines = [f"BREAKSHREDDER render {name}", f"video {edl.get('video')}  seed {edl.get('seed')}  bpm {bpm:g}  fps {fps}"]

    # ---- flatten the bars into one list of events with absolute times --------
    mute = edl.get("mute") or {}                  # instruments switched off in the page
    mix = edl.get("mix") if isinstance(edl.get("mix"), dict) else {}
    # Mixer, same routing as the page: slices x Samples; each pitched note x its own level x Instruments
    # (an oscillator note's own level is Synth); the whole mix x Master, before the limiter.
    samples_gain, instruments_gain, master_gain = level(mix.get("samples")), level(mix.get("instruments")), level(mix.get("master"))
    log_lines.append("mixer: " + "  ".join(f"{k} {mix.get(k, 100)}" for k in
                                           ("samples", "instruments", "master", "SUB", "REESE", "BOX", "ACID", "SYNTH", "DRUMS")))
    events, synth, drums, beat = [], [], [], 0.0
    for bar in edl.get("bars") or []:
        for d in bar.get("drums") or []:          # the added drum kit (sound only: it never drives the picture)
            if not mute.get("DRUMS"):
                pic_slice = int(d["s"]) if "s" in d and 0 <= int(d["s"]) < len(slices) else None
                drums.append({"when": (beat + float(d["t"])) * spb, "drum": d.get("drum"), "g": float(d.get("g", 1)),
                              "s": pic_slice, "d": float(d["d"]) * spb if "d" in d else None})
        for e in bar.get("synth") or []:
            if mute.get("SYNTH") if "s" not in e else mute.get(e.get("voice")):
                continue                          # source notes follow their voice switch, oscillator notes the Synth switch
            if "s" in e and not 0 <= int(e["s"]) < len(slices):
                raise RenderError("The edit list points at a slice that no longer exists. Press Generate and retry.")
            # A note with a retrigger step ("rt", beats) is a row of short notes that each start the sound again:
            # same chopping as playNote in the page. Only the first one keeps a slide.
            step, whole, at, pieces = float(e.get("rt") or 0), float(e["d"]), 0.0, []
            if step > 0:
                while whole - at > 0.02:
                    pieces.append((at, min(step, whole - at)))
                    at += step
            else:
                pieces.append((0.0, whole))
            for k, (at, length) in enumerate(pieces):
                synth.append({"when": (beat + float(e["t"]) + at) * spb, "dur": length * spb, "voice": e.get("voice"),
                          "note": float(e.get("note") or 69), "from": float(e["from"]) if "from" in e and not k else None,
                          "g": float(e.get("g", 0.5)),
                          # mixer level, applied AFTER the note's own processing (drive, bits...), as in the page
                          "mg": instruments_gain * level(mix.get(e.get("voice") if "s" in e else "SYNTH")),
                          "cents": float(e.get("cents") or 0), "acc": bool(e.get("acc")),
                          "s": int(e["s"]) if "s" in e else None, "rate": float(e.get("rate") or 1),
                          "rate0": float(e.get("rate0") or 0) if not k else 0.0})
        for e in bar.get("events") or []:
            if mute.get(e.get("role", "SNARE")):
                continue
            index = int(e["s"])
            if not 0 <= index < len(slices):
                raise RenderError("The edit list points at a slice that no longer exists. Press Generate and retry.")
            events.append({"when": (beat + float(e["t"])) * spb, "dur": float(e["d"]) * spb, "s": index,
                           "role": e.get("role", "SNARE"), "g": float(e.get("g", 1)) * samples_gain, "rate": float(e.get("rate") or 1),
                           "rate2": float(e["rate2"]) if e.get("rate2") else 0.0, "rev": bool(e.get("rev")),
                           "op": e.get("op", "HIT"), "grain": float(e.get("grain") or 40), "seed": int(e.get("seed") or 0)})
        beat += float(bar["beats"])
    if not events and not synth and not drums:
        raise RenderError("Nothing to render: the edit list is empty or every instrument is switched off.")
    total = beat * spb
    if total > 600:
        raise RenderError("The arrangement is longer than ten minutes. Use fewer bars.")
    events.sort(key=lambda e: e["when"])

    # ---- sound ----------------------------------------------------------------
    def sound_step(fraction, message):            # the sound is the whole job for an audio export, a small part otherwise
        progress(100 * fraction if mode == "audio" else 3 + 10 * fraction, message)

    log_lines.append("export: " + EXPORT_MODES[mode])
    sound_step(0.02, "Working out the sound: slices...")
    wav_path = cache_dir / "audio.wav"
    if not wav_path.exists():
        raise RenderError("The audio for this video is missing. Press Analyze again.")
    clips = {}
    with wave.open(str(wav_path), "rb") as src:
        if src.getframerate() != SR or src.getsampwidth() != 2:
            raise RenderError("The cached audio is in an unexpected format. Press Analyze again.")
        channels = src.getnchannels()
        for index in sorted({e["s"] for e in events} | {e["s"] for e in synth if e["s"] is not None}):
            first = max(0, min(src.getnframes(), int(round(slices[index]["start"] * SR))))
            count = max(1, min(src.getnframes() - first, int(round((slices[index]["end"] - slices[index]["start"]) * SR))))
            src.setpos(first)
            data = np.frombuffer(src.readframes(count), dtype=np.int16).astype(np.float32) / 32768.0
            data = data.reshape(-1, channels)
            clips[index] = data if channels == 2 else np.repeat(data[:, :1], 2, axis=1)

    out = np.zeros((int(math.ceil(total * SR)) + SR // 4, 2), dtype=np.float32)

    def add(at_seconds, block):
        a = int(round(at_seconds * SR))
        b = min(len(out), a + len(block))
        if a < len(out) and b > a:
            out[a:b] += block[: b - a]

    for e in events:
        clip = clips[e["s"]]
        src_len = len(clip) / SR
        if e["op"] == "STRETCH":
            r = rng32(e["seed"])
            grain = min(e["grain"] / 1000.0, src_len)
            hop = grain / 2.0
            count = max(1, int(math.ceil(e["dur"] / hop)))
            n = max(2, int(grain * SR))
            window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))).astype(np.float32)[:, None] * e["g"]
            for k in range(count):
                pos = max(0.0, min(src_len - grain, (k / count) * src_len * 0.6 + (r() - 0.5) * grain))
                a = int(pos * SR)
                seg = clip[a:a + n]
                add(e["when"] + k * hop, seg * window[: len(seg)])
            continue
        dur = e["dur"] if e["rate2"] else min(e["dur"], src_len / e["rate"])
        if dur < 0.004:
            continue
        source = clip[::-1] if e["rev"] else clip
        n = int(dur * SR)
        t = np.arange(n, dtype=np.float64) / SR
        if e["rate2"] and abs(e["rate2"] - e["rate"]) > 1e-9:
            k = e["rate2"] / e["rate"]
            pos = e["rate"] * dur / math.log(k) * (np.power(k, t / dur) - 1.0) * SR
        else:
            pos = t * e["rate"] * SR
        valid = pos < len(source) - 1
        i0 = np.minimum(pos.astype(np.int64), len(source) - 2) if len(source) > 1 else np.zeros(n, dtype=np.int64)
        frac = (pos - i0).astype(np.float32)[:, None]
        block = source[i0] * (1 - frac) + source[np.minimum(i0 + 1, len(source) - 1)] * frac
        block[~valid] = 0
        fade = min(0.003, dur / 3.0)
        nf = max(1, int(fade * SR))
        env = np.ones(n, dtype=np.float32)
        env[:nf] = np.linspace(0, 1, nf, dtype=np.float32)
        env[-nf:] = np.minimum(env[-nf:], np.linspace(1, 0, nf, dtype=np.float32))
        add(e["when"], block * env[:, None] * e["g"])

    # Pitched voices: same maths as scheduleSynth in index.html. A note with a slice number ("s") is the source-made
    # instrument: that slice, re-pitched, in place of the oscillator, shaped by the instrument's Sound panel (P).
    # A note without one is the Synth layer's plain oscillator and always uses the default sound.
    def stereo(mono):
        return np.repeat(mono[:, None], 2, axis=1)

    def glide(a, b, seconds, t):                  # exponential slide from a to b, then steady
        return np.where(t < seconds, a * (b / a) ** (t / seconds), b)

    def looped(clip, rate):
        """The slice as an oscillator: followed by itself backwards and looped (it never runs out and has no jump
        at the loop points), read at 'rate', one value per output sample. Same as pingPong in the page."""
        loop = np.concatenate([clip, clip[::-1]]).astype(np.float64)
        pos = np.cumsum(rate) - rate
        i0 = np.floor(pos).astype(np.int64)
        frac = (pos - i0)[:, None]
        return loop[i0 % len(loop)] * (1 - frac) + loop[(i0 + 1) % len(loop)] * frac

    def lowpass(cutoff, q_db=0.0):                # the browser's lowpass formula; its resonance is in dB
        w0 = 2 * math.pi * cutoff / SR
        alpha, cosw = math.sin(w0) / (2 * 10 ** (q_db / 20)), math.cos(w0)
        return [(1 - cosw) / 2, 1 - cosw, (1 - cosw) / 2], [1 + alpha, -2 * cosw, 1 - alpha]

    def ramps(n, attack, release):                # straight fade in and out, flat between
        env = np.ones(n)
        na, nr = max(1, int(attack * SR)), max(1, int(release * SR))
        env[:na] = np.linspace(0, 1, na)
        env[-nr:] = np.linspace(1, 0, nr)
        return env[:, None]

    def drive(block, amount):                     # Drive / Distortion: same tanh curve as driveCurve in the page
        if not amount > 0:
            return block
        k = 1 + 24 * amount * amount / 10000
        return np.tanh(k * np.clip(block, -1, 1)) / math.sqrt(k)

    def crush(block, bits, rate):                 # Bits + Rate: sample, round, hold. Same sums as the page's worklet
        if bits >= 16 and rate >= SR:
            return block
        count = np.arange(len(block), dtype=np.float64)
        step = min(1.0, rate / SR)
        tick = np.floor((count + 1) * step + 1e-9) > np.floor(count * step + 1e-9)
        tick[0] = True
        held = np.maximum.accumulate(np.where(tick, count, 0)).astype(np.int64)
        taken = block[held]
        if bits < 16:
            q = 2.0 ** (bits - 1)
            taken = np.floor(taken * q + 0.5) / q
        return taken

    snd = edl.get("snd")
    chan = {}                                     # instruments using a channel effect: voice -> [everything it played, P, mixer level]

    def emit(e, block, P):
        if e["s"] is not None and (P["bits"] < 16 or P["srate"] < 44100 or P["dly"] > 0 or P["rev"] > 0 or P.get("drv", 0) > 0):
            if e["voice"] not in chan:
                chan[e["voice"]] = [np.zeros_like(out, dtype=np.float64), P, e["mg"]]
            a = int(round(e["when"] * SR))
            b = min(len(out), a + len(block))
            if a < len(out) and b > a:
                chan[e["voice"]][0][a:b] += block[: b - a]
        else:
            add(e["when"], block * e["mg"])

    if synth or drums:
        try:
            from scipy.signal import lfilter, fftconvolve
        except ImportError:
            raise RenderError("Rendering needs scipy. Run install.bat again, then retry.")
    sound_step(0.35, "Working out the sound: instruments...")
    hann64 = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(64) / 63)       # the page's grain window, 64 points

    def voiced(clip, P, n, dur, start_rate, rate, slide):
        """The source slice in place of an oscillator: same as src() in the page. It plays at a rate going from
        start_rate to rate over 'slide' seconds; with no slide, the panel's Bend does the same from Bend semitones away.
        Start: where in the slice it begins. Reverse: backwards. Loop: repeat only a tiny piece. Stretch: creep
        through the slice in overlapping grains instead of looping."""
        ts = np.arange(n, dtype=np.float64) / SR
        if start_rate == rate and P["bend"] != 0:
            start_rate, slide = rate * 2 ** (P["bend"] / 12), P["btime"] / 1000
        moving = start_rate != rate and slide >= 0.001
        if not moving:
            start_rate = rate
        length = len(clip) / SR
        off = P["pos"] / 100 * length
        if P["grain"] > 0:                        # stretch: grains, half overlapping
            size = max(0.02, P["grain"] / 1000)
            hop, pieces = size / 2, max(1, int(math.ceil(dur / (size / 2))))
            span = max(0.0, length - off - size * rate)
            source = (clip[::-1] if P["back"] >= 1 else clip).astype(np.float64)
            width = int(size * SR)
            window = np.interp(np.arange(width) / width * 63, np.arange(64), hann64)[:, None]
            total_len = n + width
            mix_buf = np.zeros((total_len, 2))
            for k in range(pieces):
                tau = k * hop
                speed = start_rate * (rate / start_rate) ** (tau / slide) if moving and tau < slide else rate
                pos = (off + span * k / pieces) * SR + np.arange(width) * speed
                i0 = np.floor(pos).astype(np.int64)
                ok = i0 < len(source) - 1
                i0 = np.minimum(i0, len(source) - 2)
                frac = (pos - i0)[:, None]
                piece = (source[i0] * (1 - frac) + source[i0 + 1] * frac) * window
                piece[~ok] = 0
                a = int(round(tau * SR))
                b = min(total_len, a + width)
                if b > a:
                    mix_buf[a:b] += piece[: b - a]
            return mix_buf[:n]
        speeds = glide(start_rate, rate, slide, ts) if moving else np.full(n, rate)
        loop = np.concatenate([clip, clip[::-1]]).astype(np.float64)
        begin = ((length if P["back"] >= 1 else 0.0) + off) * SR
        pos = np.cumsum(speeds) - speeds
        if P["loop"] > 0:                         # tiny loop: go round a short piece that starts where playback starts
            piece_len = min(len(loop) - begin, P["loop"] / 1000 * SR)
            pos = begin + np.mod(pos, max(1.0, piece_len))
        else:
            pos = begin + pos
        i0 = np.floor(pos).astype(np.int64)
        frac = (pos - i0)[:, None]
        return loop[i0 % len(loop)] * (1 - frac) + loop[(i0 + 1) % len(loop)] * frac

    for e in synth:
        voice = e["voice"]
        if voice not in SND:
            continue
        clip = clips[e["s"]] if e["s"] is not None else None
        P = sound(snd, voice, plain=clip is None)
        dur = e["dur"] * (P["len"] / 100 if voice == "SUB" else 1)
        n = int(dur * SR)
        t = np.arange(n, dtype=np.float64) / SR
        rate, rate0 = e["rate"], e["rate0"] or e["rate"]
        f1 = 440.0 * 2 ** ((e["note"] - 69) / 12 + e["cents"] / 1200)
        f0 = f1 if e["from"] is None else 440.0 * 2 ** ((e["from"] - 69) / 12)

        if voice == "BOX":                        # struck, then dying away (oscillator: sine + quiet third harmonic)
            if dur < 0.02:
                continue
            attack = min(P["att"] / 1000, dur / 2)
            if clip is not None:
                pitch = rate * 2 ** (P["tune"] / 12)
                tone = voiced(clip, P, n, dur, pitch, pitch, 0)
                if P["bright"] < 16000:           # brightness
                    tone = lfilter(*lowpass(P["bright"]), tone, axis=0)
            else:
                tone = stereo(np.sin(2 * np.pi * f1 * t) + BOX_THIRD_MIX * np.sin(2 * np.pi * 3 * f1 * t))
            decay = e["g"] * BOX_FLOOR ** np.clip((t - attack) / ((dur - attack) * P["dec"] / 100), 0, 1)
            env = np.where(t < attack, e["g"] * t / attack, decay)
            emit(e, drive(tone * env[:, None], P["dist"] if clip is not None else 0), P)

        elif voice == "REESE":                    # two copies, detuned either side of the note, through a lowpass
            if dur < REESE_ATTACK + REESE_RELEASE:
                continue
            spread = 2 ** (P["det"] / 1200)
            ring = P["res"] if clip is not None else 0
            if clip is not None:                  # width: one copy leans left, the other right
                near, far = 0.5 * (1 + P["width"] / 100), 0.5 * (1 - P["width"] / 100)
                up = voiced(clip, P, n, dur, rate * spread, rate * spread, 0)
                down = voiced(clip, P, n, dur, rate / spread, rate / spread, 0)
                pair = np.stack([near * up[:, 0] + far * down[:, 0], far * up[:, 1] + near * down[:, 1]], axis=1)
            else:
                pair = stereo(sum(0.5 * (2 * ((f * t) % 1.0) - 1) for f in (f1 * spread, f1 / spread)))
            tone = lfilter(*lowpass(P["cut"], ring), pair, axis=0)
            emit(e, drive(tone * ramps(n, REESE_ATTACK, REESE_RELEASE) * (e["g"] * 10 ** (-ring / 40)), P["dist"]), P)

        elif voice == "ACID":                     # through two resonant lowpass filters; the cutoff snaps down each note
            if dur < ACID_ATTACK + ACID_RELEASE:
                continue
            accent = P["acc"] / 100 if e["acc"] else 0.0
            slide, decay = P["slide"] / 1000, P["dec"] / 1000
            if clip is not None:
                tone = voiced(clip, P, n, dur, rate0, rate, slide)
                if P["body"] > 0:                 # body: the same again an octave down
                    tone = tone + voiced(clip, P, n, dur, rate0 / 2, rate / 2, slide) * (P["body"] / 100)
            else:
                tone = stereo(2 * ((np.cumsum(glide(f0, f1, slide, t)) / SR + 0.5) % 1.0) - 1)
            top = min(18000.0, P["cut"] * (ACID_PEAK / ACID_BASE) ** (P["env"] / 100) * (1 + (ACID_ACCENT - 1) * accent))
            z1, z2 = np.zeros((2, 2)), np.zeros((2, 2))
            for a in range(0, n, ACID_BLOCK):
                num, den = lowpass(top * (P["cut"] / top) ** min(1.0, a / SR / decay), P["res"])
                stage, z1 = lfilter(num, den, tone[a:a + ACID_BLOCK], axis=0, zi=z1)
                tone[a:a + ACID_BLOCK], z2 = lfilter(num, den, stage, axis=0, zi=z2)
            trim = 10 ** (-(P["res"] - ACID_Q) / 20)   # more resonance is turned down to stay about as loud
            level_now = e["g"] * trim * ((1 + 0.4 * accent) / 1.4 if e["acc"] else 1)
            block = tone * ramps(n, ACID_ATTACK, ACID_RELEASE) * level_now
            emit(e, drive(block, P["dist"]) * ACID_OUT if clip is not None else block, P)

        elif voice == "SUB":
            if dur < SUB_ATTACK + SUB_RELEASE:
                continue
            ring = P["res"] if clip is not None else 0
            if clip is not None:                  # the slice pitched down, through a lowpass: bass made from the source
                shift = 2 ** (P["oct"] + P["tune"] / 12)
                tone = lfilter(*lowpass(P["cut"], ring), voiced(clip, P, n, dur, rate0 * shift, rate * shift, SUB_GLIDE), axis=0)
            else:                                 # sine plus a quieter sine one octave up
                f1 = 440.0 * 2 ** ((e["note"] - 69) / 12)
                phase = 2 * np.pi * np.cumsum(glide(f0, f1, SUB_GLIDE, t)) / SR
                tone = stereo(np.sin(phase) + SUB_OCTAVE_MIX * np.sin(2 * phase))
            emit(e, drive(tone * ramps(n, SUB_ATTACK, SUB_RELEASE) * (e["g"] * 10 ** (-ring / 40)), P["drive"]), P)

    # Added drum kit: same sums as scheduleDrum in index.html. Each hit plays one of the user's samples: peak brought
    # to 1, times the drum's fixed level, the hit's level, the panel level and the mixer. It plays to its end, except
    # an open hat with a length, which the next hat cuts off.
    if drums:
        try:
            import soundfile
        except ImportError:
            raise RenderError("The added drums need the soundfile package. Run install.bat again, then retry.")
        K = sound(snd, "DRUMS")
        drum_gain = instruments_gain * level(mix.get("DRUMS"))
        counts, kit, missing, played = kit_counts(), {}, set(), 0
        pick = {k: int(min(K[DRUM_PICK[k]], max(1, counts[k]))) for k in KIT_FILES}
        for d in drums:
            drum = d["drum"]
            if drum not in KIT_FILES:
                continue
            number = pick[drum]
            if (drum, number) not in kit:
                path = kit_path(drum, number)
                if path is None:
                    kit[(drum, number)] = None
                    missing.add(f"{KIT_FILES[drum][1]} {number}")
                else:
                    data, file_rate = soundfile.read(str(path), dtype="float64", always_2d=True)
                    data = data[:, :2] if data.shape[1] >= 2 else np.repeat(data, 2, axis=1)
                    top = float(np.abs(data).max()) if len(data) else 0.0
                    kit[(drum, number)] = (data / top, file_rate) if top > 0 else None
            if kit[(drum, number)] is None:
                continue
            data, file_rate = kit[(drum, number)]
            g = d["g"] * DRUM_G[drum] * level(K[DRUM_LEVEL[drum]])
            tune = K["ktune"] if drum == "K" else K["sst"] if drum == "S" else 0
            speed = 2 ** (tune / 12) * file_rate / SR          # tuning plays the sample faster or slower
            if not g > 0 or len(data) < 2:
                continue
            pos = np.arange(int((len(data) - 1) / speed)) * speed
            i0 = pos.astype(np.int64)
            frac = (pos - i0)[:, None]
            block = (data[i0] * (1 - frac) + data[i0 + 1] * frac) * g
            if d["d"] is not None:                             # cut off by the next hat: a short fade, then nothing
                keep = int(d["d"] * SR)
                if keep < len(block):
                    block = block[: keep + int(DRUM_CHOKE * SR)]
                    if len(block) > keep:
                        block[keep:] *= np.linspace(1, 0, len(block) - keep, endpoint=False)[:, None]
            emit({"s": 0, "voice": "DRUMS", "mg": drum_gain, "when": d["when"]}, block, K)
            played += 1
        log_lines.append(f"added drums: {played} hits, kit " + "  ".join(
            f"{KIT_FILES[k][1]} {pick[k]}" for k in ("K", "S", "L", "C", "O")) + f"  percs {pick['P']} and {pick['Q']}")
        if missing:
            log_lines.append("added drums: no file for " + ", ".join(sorted(missing)))

    # Channel effects, in the page's order: bits + rate on the whole channel, then delay and reverb side by side.
    room = None
    for voice, (dry, P, mixer_gain) in chan.items():
        dry = crush(drive(dry, P.get("drv", 0)), P["bits"], P["srate"])   # (drive on the whole channel: only the added drums have it)
        mixed = dry.copy()
        if P["dly"] > 0:                          # echoes: each one 'echo_gap' later and 'feedback' times the one before
            echo_gap = max(1, int(round(P["dtime"] * spb * SR)))
            echo_gain, echo_n = (P["dly"] / 100) ** 2, 1
            while echo_gain > 0.0005 and echo_n * echo_gap < len(dry):
                mixed[echo_n * echo_gap:] += echo_gain * dry[: len(dry) - echo_n * echo_gap]
                echo_gain *= P["dfb"] / 100
                echo_n += 1
        if P["rev"] > 0:                          # room: seeded noise dying away, total energy 1; same recipe as the page
            if room is None:
                room_len = int(REVERB_SECONDS * SR)
                noise = rng32(REVERB_SEED)
                room = np.zeros((room_len, 2))
                for i in range(room_len):
                    fall = math.exp(-6.908 * i / room_len)   # 60 dB down by the end
                    room[i, 0] = (noise() * 2 - 1) * fall
                    room[i, 1] = (noise() * 2 - 1) * fall
                room /= math.sqrt(float((room[:, 0] ** 2).sum()))
            for ch in (0, 1):
                mixed[:, ch] += fftconvolve(dry[:, ch], room[:, ch])[: len(dry)] * (P["rev"] / 100) ** 2
        out += (mixed * mixer_gain).astype(np.float32)
        log_lines.append(f"effects {voice}: bits {P['bits']:g}  rate {P['srate']:g}  delay {P['dly']:g} ({P['dtime']:g} beat, "
                         f"feedback {P['dfb']:g})  reverb {P['rev']:g}")
    log_lines.append(f"synth: {len(synth)} notes")

    sound_step(0.85, "Working out the sound: final mix...")
    out *= MASTER_TRIM * master_gain              # master comes BEFORE the limiter below, so it cannot push past it
    peak = float(np.max(np.abs(out))) or 1.0
    ceiling = 10 ** (-1 / 20)                      # -1 dBFS
    if peak > ceiling:
        out *= ceiling / peak
    log_lines.append(f"sound: {len(events)} events, {total:.2f} s, peak before limiting {20 * math.log10(peak):.1f} dBFS, "
                     f"output peak {20 * math.log10(min(peak, ceiling)):.1f} dBFS")
    out_wav = renders_dir / f"{name}.wav"
    if mode != "video":                           # a silent video export leaves no sound file behind
        with wave.open(str(out_wav), "wb") as dst:
            dst.setnchannels(2)
            dst.setsampwidth(2)
            dst.setframerate(SR)
            dst.writeframes((np.clip(out[: int(math.ceil(total * SR))], -1, 1) * 32767).astype(np.int16).tobytes())
    if mode == "audio":
        (renders_dir / f"{name}.edl.json").write_text(json.dumps(edl), encoding="utf-8")
        (renders_dir / f"{name}.log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        progress(100, f"Audio export done: {total:.1f} s.")
        return {"mode": mode, "mp4": None, "wav": out_wav.name, "seconds": round(total, 2), "drift_ms": None}

    # ---- picture ----------------------------------------------------------------
    progress(15, "Collecting video frames...")
    pic = [e for e in events if e["role"] != "HAT"]
    # Added kick and snare hits can cut the picture too (the kit's "Cut picture" control): each shows the source slice
    # stored with it, until the next cut. Where one lands together with a source slice, the source slice is shown.
    kit_cuts = 0
    if drums and sound(edl.get("snd"), "DRUMS")["cut"] >= 1:
        nxt = sorted(e["when"] for e in pic)
        for d in drums:
            if d["drum"] in ("K", "S") and d["s"] is not None:
                later = [w for w in nxt if w > d["when"]]
                pic.append({"when": d["when"], "dur": max(1.0 / fps, (later[0] if later else total) - d["when"]), "s": d["s"],
                            "role": "KICK" if d["drum"] == "K" else "SNARE", "g": d["g"], "rate": 1.0, "rate2": 0.0, "rev": False,
                            "op": "HIT", "kit": True})
                kit_cuts += 1
        pic.sort(key=lambda e: (e["when"], 0 if e.get("kit") else 1))
        log_lines.append(f"picture: {kit_cuts} cuts from the added kick and snare")
    hats = [e["when"] for e in events if e["role"] == "HAT"]
    run = 0
    for k, e in enumerate(pic):                   # number the repeats inside each ratchet run
        run = run + 1 if (e["op"] == "RATCHET" and k and pic[k - 1]["op"] == "RATCHET" and pic[k - 1]["s"] == e["s"]) else 0
        e["rep"] = run
    frame_bytes = width * height * 3
    scale = (f"fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=rgb24")
    footage = {}
    used = sorted({e["s"] for e in pic})
    for n, index in enumerate(used):              # (if only the sub is on, there is no footage: the picture is black)
        s = slices[index]
        length = min(MAX_SLICE_VIDEO, max(1.0 / fps, s["end"] - s["start"]))
        r = subprocess.run([ffmpeg, "-v", "error", "-ss", f"{s['start']:.4f}", "-t", f"{length:.4f}",
                            "-i", str(cache_dir / "source.mp4"), "-an", "-vf", scale, "-f", "rawvideo", "-"],
                           capture_output=True, timeout=300, creationflags=NO_WINDOW)
        count = len(r.stdout) // frame_bytes
        if count:
            footage[index] = np.frombuffer(r.stdout[: count * frame_bytes], dtype=np.uint8).reshape(count, height, width, 3)
        else:
            footage[index] = np.zeros((1, height, width, 3), dtype=np.uint8)
        progress(15 + 25 * (n + 1) / len(used), f"Collecting video frames... {n + 1}/{len(used)}")

    out_mp4 = renders_dir / f"{name}.mp4"
    err_path = renders_dir / f"{name}.ffmpeg.txt"
    n_frames = int(math.ceil(total * fps))
    ys, xs = np.arange(height), np.arange(width)

    def zoom(img, amount):                        # punch in toward the centre by 'amount' (0..0.3)
        yy = ((ys - height / 2) / (1 + amount) + height / 2).astype(np.int64)
        xx = ((xs - width / 2) / (1 + amount) + width / 2).astype(np.int64)
        return img[yy][:, xx]

    with open(err_path, "wb") as err:
        picture_in = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
                      "-i", "-"]
        picture_out = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
        # (No "-shortest": it used to drop the last frame whenever the sound ended inside it, which made the picture of
        # this export one frame shorter than the silent one. The picture is the song length rounded up to a whole frame.)
        if mode == "video":                       # same frames, same encoder settings, no sound track at all
            command = picture_in + picture_out + ["-an", "-movflags", "+faststart", str(out_mp4)]
        else:
            command = picture_in + ["-i", str(out_wav)] + picture_out + ["-c:a", "aac", "-b:a", "320k",
                                                                          "-movflags", "+faststart", str(out_mp4)]
        enc = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=err, creationflags=NO_WINDOW)
        try:
            cur, hat_i, last_hat = -1, 0, -1.0
            seed = int(edl.get("seed") or 0)
            for f in range(n_frames):
                t = (f + 0.5) / fps               # sample each frame at its centre
                while cur + 1 < len(pic) and pic[cur + 1]["when"] <= t:
                    cur += 1
                while hat_i < len(hats) and hats[hat_i] <= t:
                    last_hat = hats[hat_i]
                    hat_i += 1
                if cur < 0:
                    img = np.zeros((height, width, 3), dtype=np.uint8)
                else:
                    e = pic[cur]
                    frames = footage[e["s"]]
                    local = min(max(0.0, t - e["when"]), e["dur"])
                    if e["op"] == "STRETCH":      # smear: creep slowly through the slice
                        offset = (local / e["dur"]) * (len(frames) / fps) * 0.6
                    else:
                        offset = source_offset(local, e["dur"], e["rate"], e["rate2"])
                    k = min(len(frames) - 1, int(offset * fps))
                    if e["rev"]:
                        k = len(frames) - 1 - k
                    img = frames[k]
                    age = t - e["when"]
                    if not effects:
                        pass
                    elif e["op"] == "RATCHET" and e["rep"]:                 # each repeat steps the zoom in
                        img = zoom(img, min(0.3, 0.035 * e["rep"]))
                    if not effects:
                        pass
                    elif e["role"] == "KICK" and age < 0.1:               # flash + punch-in, easing out
                        a = (1 - age / 0.1) ** 2
                        img = zoom(img, 0.06 * a)
                        img = (img + (255 - img.astype(np.float32)) * 0.55 * a * min(1.0, e["g"])).astype(np.uint8)
                    elif e["role"] == "SNARE" and e["op"] != "TAIL" and age < 0.12:   # hard RGB split, by hit strength
                        px = int(28 * min(1.0, e["g"]) * (1 - age / 0.12))
                        if px:
                            img = np.stack([np.roll(img[:, :, 0], -px, axis=1), img[:, :, 1],
                                            np.roll(img[:, :, 2], px, axis=1)], axis=2)
                    if effects and e["op"] == "TAIL":
                        a = local / e["dur"]
                        if e["rate2"] < 1:                                  # tape-stop: colour drains out
                            grey = img.astype(np.float32).mean(axis=2, keepdims=True)
                            img = (img * (1 - a) + grey * a).astype(np.uint8)
                        else:                                               # pitch rise: channels rotate
                            img = (img * (1 - a) + np.roll(img, 1, axis=2) * a).astype(np.uint8)
                if effects and 0 <= t - last_hat < 1.5 / fps:                           # hats: one horizontal tear
                    rnd = np.random.default_rng(seed * 100003 + f)
                    y0 = int(rnd.integers(0, height - 40))
                    band = int(rnd.integers(12, 60))
                    img = img.copy()
                    img[y0:y0 + band] = np.roll(img[y0:y0 + band], int(rnd.integers(-80, 80)), axis=1)
                enc.stdin.write(np.ascontiguousarray(img).tobytes())
                if f % 30 == 0:
                    progress(40 + 58 * f / n_frames, f"Encoding frame {f}/{n_frames}")
            enc.stdin.close()
            enc.wait(timeout=600)
        except (BrokenPipeError, OSError):
            enc.kill()
            raise RenderError("FFmpeg stopped while encoding. Details: renders\\" + err_path.name)
    if enc.returncode != 0 or not out_mp4.exists():
        raise RenderError("FFmpeg could not write the MP4. Details: renders\\" + err_path.name)
    err_path.unlink(missing_ok=True)

    # a picture change lands on the frame nearest to its sound, so it is never more than half a frame out
    drift = max(abs(math.ceil(e["when"] * fps - 0.5) / fps - e["when"]) for e in pic) if pic else 0.0
    log_lines.append(f"picture: {n_frames} frames at {fps} fps, {width}x{height}, {len(used)} slices of footage")
    log_lines.append(f"max picture-to-sound drift: {drift * 1000:.1f} ms (one frame is {1000 / fps:.1f} ms)")
    (renders_dir / f"{name}.edl.json").write_text(json.dumps(edl), encoding="utf-8")
    (renders_dir / f"{name}.log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    done = "Video export (silent) done" if mode == "video" else "Audio + video export done"
    progress(100, f"{done}: {total:.1f} s. Max drift {drift * 1000:.1f} ms.")
    return {"mode": mode, "mp4": out_mp4.name, "wav": out_wav.name if mode == "both" else None, "seconds": round(total, 2),
            "drift_ms": round(drift * 1000, 1)}
