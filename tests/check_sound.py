"""
BREAKSHREDDER - sound check for anyone changing or adding instruments.

Run from the project folder, giving it an edit list saved beside any export:

    python tests\\check_sound.py renders\\<name>.edl.json

It only works out the SOUND (export type "audio": no ffmpeg, no picture), a few times over, and prints:
  1. whether two exports of the same edit list are identical (they must be: nothing may be random);
  2. how loud each part is on its own, so a new or changed instrument can be balanced against the others;
  3. whether the mixer still scales each part exactly (catches a level applied in the wrong place);
  4. whether bypassing a sound panel gives the same sound as leaving it out of the edit list.

It checks render.py only. The page's live preview has to be listened to; see INSTRUMENTS.md.
The edit list must come from the current page (press Generate, then any Export): older ones lack newer parts.
"""
import copy
import json
import shutil
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import render  # noqa: E402

SAMPLES = ["KICK", "SNARE", "HAT", "TONAL"]                 # switches for the chopped video audio
INSTRUMENTS = ["SUB", "REESE", "BOX", "ACID", "DRUMS"]      # switches with a mixer level and a sound panel. ADD NEW ONES HERE
EVERY_SWITCH = SAMPLES + INSTRUMENTS + ["SYNTH"]


def sound(edl, analysis):
    """The exported WAV for this edit list, as numbers between -1 and 1 (two columns: left, right)."""
    tmp = Path(tempfile.mkdtemp())
    try:
        render.render(edl, analysis, ROOT / "cache" / edl["video"], tmp, "", "check", lambda pct, msg: None, mode="audio")
        with wave.open(str(tmp / "check.wav")) as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return data.reshape(-1, 2)


def same(a, b, tolerance=2 / 32768):
    return a.shape == b.shape and float(np.abs(a - b).max()) <= tolerance


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    base = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    analysis = json.loads((ROOT / "cache" / base["video"] / "analysis.json").read_text(encoding="utf-8"))
    bpm = float(base.get("bpm") or 174)
    bars = len(base["bars"])
    quiet = 0.4                                             # master 40: keeps every test under the limiter, so levels compare exactly
    trim = (quiet ** 2) * render.MASTER_TRIM

    def version(keep=None, mix=None, snd="same"):
        e = copy.deepcopy(base)
        e["mix"] = dict({"master": 100 * quiet}, **(mix or {}))
        if keep is not None:
            e["mute"] = {k: True for k in EVERY_SWITCH if k not in keep}
        if snd != "same":
            e["snd"] = snd
        return e

    def loudest_bar(x):
        step = int(len(x) / bars) or 1
        return max(float(np.sqrt((x[i:i + step] ** 2).mean())) for i in range(0, len(x) - step + 1, step)) / trim

    whole = sound(version(), analysis)
    print(f"edit list: {bars} bars at {bpm:g} BPM, {len(whole) / render.SR:.2f} s")
    print("1 two exports of the same edit list are identical :", same(whole, sound(version(), analysis)))

    print("2 loudest bar of each part on its own (the chopped video audio is the yardstick):")
    alone = {}
    for name, keep in [("chopped video audio", SAMPLES)] + [(k, [k]) for k in INSTRUMENTS + ["SYNTH"]]:
        try:
            alone[name] = sound(version(keep), analysis)
            print(f"     {name:<20} {loudest_bar(alone[name]):.3f}   peak {float(np.abs(alone[name]).max()) / trim:.2f}")
        except render.RenderError:
            print(f"     {name:<20} (nothing in this edit list)")

    print("3 its mixer slider at 50 gives exactly a quarter, and the Samples slider does not touch it:")
    for name in INSTRUMENTS + ["SYNTH"]:
        if name in alone:
            half = same(sound(version([name], {name: 50}), analysis), alone[name] * 0.25)
            untouched = same(sound(version([name], {"samples": 0}), analysis), alone[name])
            print(f"     {name:<20} {half}   {untouched}")

    print("4 a bypassed sound panel == no saved settings for it (both mean: the default sound):")
    for name in INSTRUMENTS:
        if name in alone and name in render.SND:
            plain = sound(version([name], snd={}), analysis)
            wild = {key: (lo if default != lo else hi) for key, (lo, hi, default) in render.SND[name].items()}
            bypassed = sound(version([name], snd={name: dict(wild, on=False)}), analysis)
            print(f"     {name:<20} {same(plain, bypassed)}")


if __name__ == "__main__":
    main()
