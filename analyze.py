"""
BREAKSHREDDER - analysis (milestone 2)

Takes cache/<videoID>/source.mp4 and writes, next to it:
  audio.wav      full-length 44.1 kHz stereo audio for the page to play slices from
  thumbs.jpg     one image holding a small video frame every half second
  analysis.json  tempo, onsets, slices (with class tags), scene cuts, keyframes

Slice times are always in seconds of the ORIGINAL source, even when a trim is set.
"""

import json
import math
import re
import subprocess
import time
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SR = 22050          # analysis sample rate (downsampled: plenty for onsets and classes)
N_FFT = 2048
HOP = 512
MIN_SLICE_FRAMES = 3    # about 70 ms
ENV_POINTS = 24         # points in each pad's mini waveform
THUMB_FPS = 2
THUMB_W, THUMB_H, THUMB_COLS = 96, 54, 30
LUMA_FPS = 10
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ANALYSIS_VERSION = 1


class AnalysisError(Exception):
    """An error with a message that is safe to show in the page."""


def _run(cmd, timeout=900, binary=False):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW,
                          **({} if binary else {"text": True, "encoding": "utf-8", "errors": "replace"}))


def classify(perc_ratio, centroid, low_ratio, voice_ratio, flatness, length):
    """Simple feature rules. They are a starting guess; the user can re-tag any slice."""
    if perc_ratio > 0.5:
        if low_ratio > 0.35 and centroid < 1500:
            return "KICK"
        if centroid > 4500:
            return "HAT"
        if length > 0.7 and flatness > 0.2:
            return "NOISE"
        return "SNARE"
    if flatness > 0.25:
        return "NOISE"
    if voice_ratio > 0.7 and 400 < centroid < 2800 and flatness < 0.1:
        return "VOCAL"
    return "TONAL"


def analyze(src, out_dir, ffmpeg, ffprobe, trim_in, trim_out, progress):
    """progress(percent, message) is called as the work moves along."""
    try:
        import numpy as np
        import librosa
    except ImportError:
        raise AnalysisError("Analysis needs the librosa package. Run install.bat again, then retry.")

    src, out_dir = Path(src), Path(out_dir)
    span = trim_out - trim_in
    if span < 1.0:
        raise AnalysisError("The trimmed section is shorter than one second.")
    cut = ["-ss", f"{trim_in:.3f}", "-t", f"{span:.3f}"]

    # 1) full-length audio for the page ---------------------------------
    progress(2, "Extracting audio...")
    wav = out_dir / "audio.wav"
    if not wav.exists():
        r = _run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "2", "-ar", "44100",
                  "-c:a", "pcm_s16le", str(wav)])
        if r.returncode != 0 or not wav.exists():
            raise AnalysisError("This video has no audio track that could be read.")

    # 2) downsampled mono audio straight into memory ---------------------
    r = _run([ffmpeg, "-v", "error"] + cut + ["-i", str(src), "-vn", "-ac", "1", "-ar", str(SR),
              "-f", "f32le", "-"], binary=True)
    y = np.frombuffer(r.stdout, dtype=np.float32).copy()
    if y.size < SR:
        raise AnalysisError("Not enough audio to analyze.")
    peak = float(np.max(np.abs(y))) or 1.0

    # 3) audio features ---------------------------------------------------
    progress(10, "Separating drums from tones...")
    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)).astype(np.float32)
    H, P = librosa.decompose.hpss(S)
    n_frames = S.shape[1]

    progress(35, "Finding hits and tempo...")
    env = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tempo, _ = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP)
    bpm = float(np.atleast_1d(tempo)[0])
    peaks = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, backtrack=False)
    starts = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP, backtrack=True)
    env_max = float(env.max()) or 1.0

    progress(45, "Measuring slices...")
    freqs = librosa.fft_frequencies(sr=SR, n_fft=N_FFT)
    S2 = S ** 2
    e_tot = S2.sum(axis=0) + 1e-12
    e_p = (P ** 2).sum(axis=0)
    e_h = (H ** 2).sum(axis=0)
    e_low = S2[freqs < 150].sum(axis=0)
    e_voice = S2[(freqs >= 300) & (freqs <= 3400)].sum(axis=0)
    cent = (freqs[:, None] * S).sum(axis=0) / (S.sum(axis=0) + 1e-9)
    flat = librosa.feature.spectral_flatness(S=S)[0]
    chroma = librosa.feature.chroma_stft(S=H ** 2, sr=SR, n_fft=N_FFT, hop_length=HOP)
    del S2

    def frame_time(f):
        return trim_in + f * HOP / SR

    onsets = []
    for k in range(min(len(peaks), len(starts))):
        f0 = int(starts[k])
        f1 = min(n_frames, f0 + 6)
        pr = float(e_p[f0:f1].sum() / (e_p[f0:f1].sum() + e_h[f0:f1].sum() + 1e-12))
        onsets.append({"t": round(frame_time(f0), 4),
                       "strength": round(float(env[min(int(peaks[k]), len(env) - 1)]) / env_max, 3),
                       "cls": "percussive" if pr > 0.5 else "harmonic"})

    # slice boundaries: start, every onset, end; drop slices that are too short
    bounds = [0]
    for f in sorted(set(int(s) for s in starts)):
        if f - bounds[-1] >= MIN_SLICE_FRAMES:
            bounds.append(f)
    if n_frames - bounds[-1] < MIN_SLICE_FRAMES and len(bounds) > 1:
        bounds.pop()
    bounds.append(n_frames)

    # 4) video measurements ----------------------------------------------
    progress(55, "Reading picture brightness and motion...")
    luma = motion = None
    r = _run([ffmpeg, "-v", "error"] + cut + ["-i", str(src), "-an",
              "-vf", f"fps={LUMA_FPS},scale=32:18,format=gray", "-f", "rawvideo", "-"], binary=True)
    if r.returncode == 0 and len(r.stdout) >= 32 * 18:
        frames = np.frombuffer(r.stdout, dtype=np.uint8)
        frames = frames[: (frames.size // 576) * 576].reshape(-1, 576).astype(np.float32) / 255.0
        luma = frames.mean(axis=1)
        motion = np.concatenate([[0.0], np.abs(np.diff(frames, axis=0)).mean(axis=1)])

    progress(68, "Finding scene cuts...")
    scene_cuts = []
    r = _run([ffmpeg, "-v", "info", "-nostats"] + cut + ["-i", str(src), "-an",
              "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo", "-f", "null", "-"])
    for line in (r.stderr or "").splitlines():
        if "showinfo" in line:
            m = re.search(r"pts_time:\s*([0-9.]+)", line)
            if m:
                scene_cuts.append(round(trim_in + float(m.group(1)), 3))

    keyframes = []
    if ffprobe:
        r = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                  "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(src)])
        for line in (r.stdout or "").splitlines():
            try:
                keyframes.append(round(float(line.strip().strip(",")), 3))
            except ValueError:
                pass

    progress(80, "Making thumbnails...")
    thumb_count = int(math.ceil(span * THUMB_FPS))
    rows = max(1, int(math.ceil(thumb_count / THUMB_COLS)))
    thumbs_path = out_dir / "thumbs.jpg"
    r = _run([ffmpeg, "-y", "-v", "error"] + cut + ["-i", str(src), "-an", "-frames:v", "1", "-q:v", "5",
              "-vf", (f"fps={THUMB_FPS},scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
                      f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2,format=gray,tile={THUMB_COLS}x{rows}"),
              str(thumbs_path)])
    has_thumbs = r.returncode == 0 and thumbs_path.exists()

    # 5) build the slice list ---------------------------------------------
    progress(90, "Tagging slices...")
    slices = []
    counts = {}
    for i in range(len(bounds) - 1):
        f0, f1 = bounds[i], bounds[i + 1]
        a1 = min(f1, f0 + 6)                      # the first ~140 ms decides drum classes
        seg = y[f0 * HOP: min(len(y), f1 * HOP)]
        if seg.size == 0:
            continue
        start, end = frame_time(f0), min(trim_out, frame_time(f1))
        pr = float(e_p[f0:a1].sum() / (e_p[f0:a1].sum() + e_h[f0:a1].sum() + 1e-12))
        centroid = float(np.average(cent[f0:a1], weights=e_tot[f0:a1]))
        low_ratio = float(e_low[f0:a1].sum() / e_tot[f0:a1].sum())
        voice_ratio = float(e_voice[f0:f1].sum() / e_tot[f0:f1].sum())
        flatness = float(flat[f0:f1].mean())
        tag = classify(pr, centroid, low_ratio, voice_ratio, flatness, end - start)
        counts[tag] = counts.get(tag, 0) + 1

        chunks = np.array_split(np.abs(seg), ENV_POINTS)
        envelope = [int(min(255, round(255 * float(c.max()) / peak))) if c.size else 0 for c in chunks]

        item = {"i": len(slices), "start": round(start, 4), "end": round(end, 4),
                "rms": round(float(np.sqrt(np.mean(seg ** 2))) / peak, 4),
                "centroid": round(centroid, 1),
                "note": NOTES[int(np.argmax(chroma[:, f0:f1].mean(axis=1)))],
                "perc": round(pr, 3), "tag": tag, "env": envelope}
        if luma is not None and len(luma):
            v0 = min(len(luma) - 1, int((start - trim_in) * LUMA_FPS))
            v1 = max(v0 + 1, min(len(luma), int(math.ceil((end - trim_in) * LUMA_FPS))))
            item["luma"] = round(float(luma[v0:v1].mean()), 3)
            item["motion"] = round(float(motion[v0:v1].mean()), 4)
        slices.append(item)

    result = {
        "version": ANALYSIS_VERSION, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trim_in": round(trim_in, 3), "trim_out": round(trim_out, 3),
        "sr": SR, "bpm": round(bpm, 2),
        "onsets": onsets, "slices": slices, "counts": counts,
        "scene_cuts": scene_cuts, "keyframes": keyframes,
        "thumbs": ({"fps": THUMB_FPS, "w": THUMB_W, "h": THUMB_H, "cols": THUMB_COLS,
                    "rows": rows, "count": thumb_count, "gray": True} if has_thumbs else None),
    }
    (out_dir / "analysis.json").write_text(json.dumps(result), encoding="utf-8")
    progress(100, f"{len(slices)} slices, {bpm:.1f} BPM, {len(scene_cuts)} scene cuts")
    return result
