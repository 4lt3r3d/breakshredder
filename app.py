"""
BREAKSHREDDER - local server (milestone 1)

What this file does right now:
  - finds the helper tools (yt-dlp, ffmpeg, ffprobe, a JavaScript runtime)
  - downloads a YouTube video into cache/<videoID>/source.mp4
  - serves that file back to the page so it can be played
  - runs the analysis in analyze.py and stores the slice bank (milestone 2)
Later milestones add the edit list and the offline render.

Run it with start.bat, then open http://localhost:5077
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file

ROOT = Path(__file__).resolve().parent
BIN = ROOT / "bin"
CACHE = ROOT / "cache"
RENDERS = ROOT / "renders"
CONFIG_PATH = ROOT / "config.json"
INDEX_PATH = ROOT / "index.html"

DEFAULT_CONFIG = {
    "port": 5077,
    "max_source_minutes": 15,
    "max_height": 1080,
    "open_browser": True,
    # Optional full paths, used only if a tool is not in .\bin or on PATH.
    "tool_paths": {"yt-dlp": "", "ffmpeg": "", "ffprobe": "", "deno": "", "node": ""},
}

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
URL_ID_RES = [
    re.compile(r"(?:youtube\.com|youtube-nocookie\.com)/watch\?(?:.*&)?v=([A-Za-z0-9_-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_-]{11})"),
    re.compile(r"youtube\.com/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})"),
]

# Hide the black console window that Windows opens for each helper program.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

app = Flask(__name__, static_folder=None)
jobs = {}
analysis_jobs = {}
render_jobs = {}
RENDER_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(mp4|wav)$")
jobs_lock = threading.Lock()
MEDIA_FILES = {"source.mp4": "video/mp4", "audio.wav": "audio/wav", "thumbs.jpg": "image/jpeg"}


# ---------------------------------------------------------------- config

def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for key, value in user.items():
                if key == "tool_paths" and isinstance(value, dict):
                    cfg["tool_paths"].update(value)
                else:
                    cfg[key] = value
        except (ValueError, OSError):
            pass  # a broken config.json falls back to defaults; /api/status reports it
    else:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def config_problem():
    if not CONFIG_PATH.exists():
        return None
    try:
        json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return None
    except (ValueError, OSError):
        return "config.json could not be read (check for a missing comma or quote). Using defaults."


# ---------------------------------------------------------------- tool detection

def find_tool(name):
    """Look in .\\bin, then PATH, then config.json. Returns (path, where) or (None, None)."""
    for candidate in (BIN / f"{name}.exe", BIN / name):
        if candidate.is_file():
            return str(candidate), "bin"
    on_path = shutil.which(name)
    if on_path:
        return on_path, "PATH"
    configured = (load_config().get("tool_paths") or {}).get(name) or ""
    if configured:
        p = Path(configured)
        if p.is_dir():
            for candidate in (p / f"{name}.exe", p / name):
                if candidate.is_file():
                    return str(candidate), "config.json"
        elif p.is_file():
            return str(p), "config.json"
    return None, None


def ytdlp_command():
    """yt-dlp as a program, or as a Python module if it was installed with pip."""
    path, where = find_tool("yt-dlp")
    if path:
        return [path], path, where
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"], "python -m yt_dlp", "pip"
    return None, None, None


def js_runtime():
    """YouTube downloads need a JavaScript runtime. Deno is yt-dlp's default; Node also works."""
    for name in ("deno", "node"):
        path, where = find_tool(name)
        if path:
            return name, path, where
    return None, None, None


def js_runtime_args():
    name, path, where = js_runtime()
    if not name:
        return []
    if name == "deno" and where == "PATH":
        return []  # yt-dlp finds this one by itself
    return ["--js-runtimes", f"{name}:{path}"]


def tool_version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        text = (out.stdout or out.stderr or "").strip()
        return text.splitlines()[0][:80] if text else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def gather_status(with_versions=True):
    tools = {}
    problems = []

    cmd, shown, where = ytdlp_command()
    tools["yt-dlp"] = {"found": bool(cmd), "path": shown, "source": where,
                       "version": tool_version(cmd + ["--version"]) if cmd and with_versions else ""}
    if not cmd:
        problems.append("yt-dlp is missing. Run install.bat, or put yt-dlp.exe in the bin folder.")

    for name in ("ffmpeg", "ffprobe"):
        path, where = find_tool(name)
        tools[name] = {"found": bool(path), "path": path, "source": where,
                       "version": tool_version([path, "-version"]) if path and with_versions else ""}
        if not path:
            problems.append(f"{name} is missing. Put {name}.exe in the bin folder, "
                            f"or set its path in config.json.")

    name, path, where = js_runtime()
    tools["js-runtime"] = {"found": bool(name), "name": name, "path": path, "source": where,
                           "version": tool_version([path, "--version"]) if path and with_versions else ""}
    if not name:
        problems.append("No JavaScript runtime found (Deno or Node). YouTube downloads may fail "
                        "or miss formats without one. Put deno.exe in the bin folder.")

    cfg_issue = config_problem()
    if cfg_issue:
        problems.append(cfg_issue)

    can_ingest = tools["yt-dlp"]["found"] and tools["ffmpeg"]["found"]
    return {"tools": tools, "problems": problems, "can_ingest": can_ingest,
            "config": {k: v for k, v in load_config().items() if k != "tool_paths"}}


# ---------------------------------------------------------------- ingest

def extract_video_id(url):
    url = (url or "").strip()
    for rx in URL_ID_RES:
        m = rx.search(url)
        if m:
            return m.group(1)
    return None


def friendly_error(text):
    """Turn yt-dlp's error output into one plain sentence."""
    t = (text or "").lower()
    if "confirm your age" in t or "age-restricted" in t or "inappropriate for some users" in t:
        return "This video is age-restricted, so YouTube will not serve it without a signed-in account."
    if "not a bot" in t:
        return "YouTube asked for a sign-in check (bot detection). Wait a few minutes and try again."
    if "private video" in t:
        return "This video is private."
    if "video unavailable" in t or "has been removed" in t or "account associated" in t:
        return "This video is unavailable or has been removed."
    if "not available in your country" in t or "geo" in t and "restrict" in t:
        return "This video is blocked in your region."
    if "members-only" in t or "join this channel" in t:
        return "This video is members-only."
    if "live event will begin" in t or "premieres in" in t:
        return "This video has not started yet (upcoming live stream or premiere)."
    if "javascript runtime" in t or "js runtime" in t or "no supported javascript" in t:
        return "yt-dlp needs a JavaScript runtime for YouTube. Put deno.exe in the bin folder and retry."
    if "ffmpeg" in t and ("not found" in t or "not installed" in t):
        return "FFmpeg was not found, so the video and audio could not be joined."
    if "getaddrinfo" in t or "timed out" in t or "connection" in t and "reset" in t:
        return "Network problem while reaching YouTube. Check your connection and retry."
    if "requested format is not available" in t:
        return "No downloadable format was offered for this video. Updating yt-dlp usually fixes this."
    if "http error 403" in t:
        return "YouTube refused the download (403). Updating yt-dlp usually fixes this."
    for line in (text or "").splitlines():
        if line.strip().upper().startswith("ERROR"):
            return "Download failed: " + line.split(":", 1)[-1].strip()[:200]
    return "Download failed for an unknown reason. Details are in the console window."


def job_log(job, message):
    job["log"].append({"t": time.strftime("%H:%M:%S"), "msg": message})


def read_meta(video_id):
    meta_path = CACHE / video_id / "meta.json"
    if meta_path.exists() and (CACHE / video_id / "source.mp4").exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
    return None


def run_ingest(job, url):
    video_id = job["id"]
    cfg = load_config()
    try:
        cmd, _, _ = ytdlp_command()
        ffmpeg, _ = find_tool("ffmpeg")
        if not cmd:
            raise RuntimeError("yt-dlp is missing. Run install.bat, or put yt-dlp.exe in the bin folder.")
        if not ffmpeg:
            raise RuntimeError("ffmpeg is missing. Put ffmpeg.exe and ffprobe.exe in the bin folder.")
        if not js_runtime()[0]:
            job_log(job, "WARNING: no Deno/Node found. Trying anyway; it may fail.")

        common = cmd + ["--no-playlist", "--no-warnings", "--encoding", "utf-8"] + js_runtime_args()

        # 1) Ask YouTube about the video before downloading anything.
        job["stage"] = "probe"
        job_log(job, "Asking YouTube about the video...")
        probe = subprocess.run(
            common + ["--skip-download", "--print", "%(id)s\t%(duration)s\t%(is_live)s\t%(title)s", url],
            capture_output=True, text=True, timeout=120,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        if probe.returncode != 0:
            print(probe.stderr, file=sys.stderr)
            raise RuntimeError(friendly_error(probe.stderr))
        parts = probe.stdout.strip().splitlines()[-1].split("\t", 3)
        if len(parts) < 4:
            raise RuntimeError("YouTube returned an answer this tool could not read.")
        _, duration_raw, is_live, title = parts
        if is_live == "True":
            raise RuntimeError("Live streams are not supported. Wait until the stream has ended.")
        try:
            duration = float(duration_raw)
        except ValueError:
            raise RuntimeError("YouTube did not report a length for this video, so it was skipped.")
        limit_min = float(cfg.get("max_source_minutes", 15))
        if duration > limit_min * 60:
            raise RuntimeError(
                f"Source is {duration / 60:.1f} minutes. The limit is {limit_min:g} minutes "
                f"(change max_source_minutes in config.json to raise it).")
        job["title"] = title
        job["duration"] = duration
        job_log(job, f"Found: {title} ({duration:.0f} s)")

        # 2) Download best video (up to max height) + best audio, joined into one MP4.
        out_dir = CACHE / video_id
        out_dir.mkdir(parents=True, exist_ok=True)
        max_h = int(cfg.get("max_height", 1080))
        dl_cmd = common + [
            "-f", "bv*+ba/b",
            "-S", f"res:{max_h},ext:mp4:m4a",
            "--merge-output-format", "mp4",
            "--ffmpeg-location", str(Path(ffmpeg).parent),
            "--newline",
            "--progress-template", "download:BS|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
            "-o", str(out_dir / "source.%(ext)s"),
            url,
        ]
        job["stage"] = "download"
        job_log(job, "Downloading...")
        proc = subprocess.Popen(dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        tail = []
        part = 0
        last_pct = 0.0
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            if line.startswith("BS|"):
                bits = line.split("|")
                try:
                    pct = float(bits[1].replace("%", "").strip())
                except (ValueError, IndexError):
                    continue
                if pct < last_pct - 50:
                    part += 1  # second stream (audio) has started
                last_pct = pct
                # video is ~90% of the bytes, audio the rest
                job["progress"] = round(pct * 0.9 if part == 0 else 90 + pct * 0.09, 1)
                job["speed"] = bits[2].strip() if len(bits) > 2 else ""
                job["eta"] = bits[3].strip() if len(bits) > 3 else ""
                continue
            tail.append(line)
            tail[:] = tail[-40:]
            if line.startswith("[Merger]"):
                job["stage"] = "merge"
                job["progress"] = 99.0
                job_log(job, "Joining video and audio...")
            elif line.upper().startswith("ERROR"):
                print(line, file=sys.stderr)
        proc.wait()
        source = out_dir / "source.mp4"
        if proc.returncode != 0 or not source.exists():
            raise RuntimeError(friendly_error("\n".join(tail)))

        meta = {"id": video_id, "title": title, "duration": duration, "url": url,
                "bytes": source.stat().st_size, "fetched": time.strftime("%Y-%m-%d %H:%M:%S")}
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        job.update(stage="done", state="done", progress=100.0, meta=meta)
        job_log(job, f"Cached {meta['bytes'] / 1048576:.1f} MB to cache\\{video_id}")
    except subprocess.TimeoutExpired:
        job.update(state="error", error="YouTube took too long to answer. Try again.")
        job_log(job, "ERROR: " + job["error"])
    except RuntimeError as exc:
        job.update(state="error", error=str(exc))
        job_log(job, "ERROR: " + str(exc))
    except Exception as exc:  # anything unexpected: plain message in the page, detail in the console
        print(f"[ingest] unexpected error: {exc!r}", file=sys.stderr)
        job.update(state="error", error="Something unexpected went wrong. Details are in the console window.")
        job_log(job, "ERROR: " + job["error"])


# ---------------------------------------------------------------- routes

@app.get("/")
def index():
    if INDEX_PATH.exists():
        return send_file(INDEX_PATH, max_age=0)
    return ("BREAKSHREDDER server is running. The page (index.html) has not been built yet.\n"
            "Tool check: http://localhost:%d/api/status\n" % load_config().get("port", 5077),
            200, {"Content-Type": "text/plain; charset=utf-8"})


# The program files as they were when this server window was started. A running server keeps using those old
# copies, so if one changes on disk the page is told, and asks for the window to be closed and start.bat run again.
WATCHED = ("app.py", "render.py", "analyze.py")


def file_stamps():
    return {name: (ROOT / name).stat().st_mtime if (ROOT / name).exists() else 0 for name in WATCHED}


STARTED_WITH = file_stamps()


@app.get("/api/status")
def api_status():
    status = gather_status()
    now = file_stamps()
    status["stale"] = [name for name in WATCHED if now[name] != STARTED_WITH[name]]
    return jsonify(status)


@app.get("/api/cache")
def api_cache():
    items = []
    if CACHE.exists():
        for d in sorted(CACHE.iterdir()):
            if d.is_dir() and VIDEO_ID_RE.match(d.name):
                meta = read_meta(d.name)
                if meta:
                    items.append(meta)
    items.sort(key=lambda m: m.get("fetched", ""), reverse=True)
    return jsonify({"items": items})


@app.post("/api/ingest")
def api_ingest():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    video_id = extract_video_id(url)
    if not video_id:
        return jsonify({"ok": False, "error": "That does not look like a YouTube video link."}), 400

    meta = read_meta(video_id)
    if meta:  # already cached: instant
        return jsonify({"ok": True, "id": video_id, "cached": True, "meta": meta})

    with jobs_lock:
        job = jobs.get(video_id)
        if not job or job["state"] != "running":
            job = {"id": video_id, "state": "running", "stage": "queued", "progress": 0.0,
                   "speed": "", "eta": "", "title": "", "log": [], "error": None, "meta": None}
            jobs[video_id] = job
            threading.Thread(target=run_ingest, args=(job, url), daemon=True).start()
    return jsonify({"ok": True, "id": video_id, "cached": False})


@app.get("/api/job/<video_id>")
def api_job(video_id):
    if not VIDEO_ID_RE.match(video_id):
        abort(404)
    job = jobs.get(video_id)
    if not job:
        meta = read_meta(video_id)
        if meta:
            return jsonify({"id": video_id, "state": "done", "stage": "done", "progress": 100.0,
                            "log": [], "error": None, "meta": meta})
        abort(404)
    return jsonify(job)


@app.get("/media/<video_id>/<name>")
def media_file(video_id, name):
    if not VIDEO_ID_RE.match(video_id) or name not in MEDIA_FILES:
        abort(404)
    path = CACHE / video_id / name
    if not path.exists():
        abort(404)
    # conditional=True lets the browser seek (HTTP range requests)
    return send_file(path, mimetype=MEDIA_FILES[name], conditional=True, max_age=0)


@app.get("/api/kit")
def api_kit():
    """How many samples of each added drum the drumnbasskit folder holds."""
    import render
    counts = render.kit_counts()
    return jsonify({"ok": all(counts.values()), "counts": counts})


@app.get("/kit/<drum>/<int:number>.wav")
def kit_file(drum, number):
    """One sample of the added drum kit, exactly as it is on disk (the same file render.py reads)."""
    import render
    path = render.kit_path(drum, number)
    if path is None:
        abort(404)
    return send_file(path, mimetype="audio/wav", conditional=True, max_age=0)


@app.get("/media/<video_id>/slice/<int:index>.wav")
def media_slice(video_id, index):
    """One slice of the audio as a small WAV file, so the page never has to load the whole song."""
    import io
    import wave
    if not VIDEO_ID_RE.match(video_id):
        abort(404)
    times = slice_times(video_id)
    path = CACHE / video_id / "audio.wav"
    if times is None or index < 0 or index >= len(times) or not path.exists():
        abort(404)
    start, end = times[index]
    with wave.open(str(path), "rb") as src:
        rate = src.getframerate()
        first = max(0, min(src.getnframes(), int(round(start * rate))))
        count = max(1, min(src.getnframes() - first, int(round((end - start) * rate))))
        src.setpos(first)
        frames = src.readframes(count)
        out = io.BytesIO()
        with wave.open(out, "wb") as dst:
            dst.setnchannels(src.getnchannels())
            dst.setsampwidth(src.getsampwidth())
            dst.setframerate(rate)
            dst.writeframes(frames)
    return Response(out.getvalue(), mimetype="audio/wav", headers={"Cache-Control": "max-age=3600"})


_slice_times = {}


def slice_times(video_id):
    """Start/end of every slice, remembered until the analysis file changes."""
    path = CACHE / video_id / "analysis.json"
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    hit = _slice_times.get(video_id)
    if hit and hit[0] == stamp:
        return hit[1]
    data = read_analysis(video_id)
    if not data:
        return None
    times = [(s["start"], s["end"]) for s in data["slices"]]
    _slice_times[video_id] = (stamp, times)
    return times


# ---------------------------------------------------------------- analysis (milestone 2)

def read_analysis(video_id):
    path = CACHE / video_id / "analysis.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def read_overrides(video_id):
    """The user's own changes to slices (re-tag, lock, delete), kept apart from the analysis."""
    path = CACHE / video_id / "slices_user.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (ValueError, OSError):
        return {}


def run_analysis(job, video_id, trim_in, trim_out):
    import analyze

    def progress(pct, message):
        job["progress"] = pct
        job_log(job, message)

    try:
        ffmpeg, _ = find_tool("ffmpeg")
        ffprobe, _ = find_tool("ffprobe")
        if not ffmpeg:
            raise analyze.AnalysisError("ffmpeg is missing. Put ffmpeg.exe in the bin folder.")
        out_dir = CACHE / video_id
        analyze.analyze(out_dir / "source.mp4", out_dir, ffmpeg, ffprobe, trim_in, trim_out, progress)
        user_file = out_dir / "slices_user.json"   # slice numbers changed, so old edits no longer apply
        if user_file.exists():
            user_file.write_text("{}", encoding="utf-8")
        job.update(state="done", progress=100.0)
    except analyze.AnalysisError as exc:
        job.update(state="error", error=str(exc))
        job_log(job, "ERROR: " + str(exc))
    except MemoryError:
        job.update(state="error", error="Ran out of memory. Trim the source to a shorter section and retry.")
        job_log(job, "ERROR: " + job["error"])
    except subprocess.TimeoutExpired:
        job.update(state="error", error="FFmpeg took too long on this file.")
        job_log(job, "ERROR: " + job["error"])
    except Exception as exc:
        print(f"[analysis] unexpected error: {exc!r}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        job.update(state="error", error="Analysis failed unexpectedly. Details are in the console window.")
        job_log(job, "ERROR: " + job["error"])


@app.post("/api/analyze")
def api_analyze():
    data = request.get_json(silent=True) or {}
    video_id = data.get("id") or ""
    if not VIDEO_ID_RE.match(video_id):
        abort(404)
    meta = read_meta(video_id)
    if not meta:
        return jsonify({"ok": False, "error": "Fetch the video first."}), 400
    duration = float(meta["duration"])
    try:
        trim_in = max(0.0, float(data.get("trim_in") or 0))
        trim_out = float(data.get("trim_out") or duration)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Trim points must be numbers."}), 400
    trim_out = min(duration, trim_out)
    if trim_out - trim_in < 1.0:
        return jsonify({"ok": False, "error": "The section between IN and OUT must be at least one second."}), 400

    existing = read_analysis(video_id)
    if (existing and not data.get("force")
            and abs(existing.get("trim_in", 0) - trim_in) < 0.01
            and abs(existing.get("trim_out", 0) - trim_out) < 0.01):
        return jsonify({"ok": True, "cached": True})

    with jobs_lock:
        job = analysis_jobs.get(video_id)
        if not job or job["state"] != "running":
            job = {"id": video_id, "state": "running", "progress": 0.0, "log": [], "error": None}
            analysis_jobs[video_id] = job
            threading.Thread(target=run_analysis, args=(job, video_id, trim_in, trim_out), daemon=True).start()
    return jsonify({"ok": True, "cached": False})


@app.get("/api/analyze/job/<video_id>")
def api_analyze_job(video_id):
    job = analysis_jobs.get(video_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.get("/api/analysis/<video_id>")
def api_analysis(video_id):
    if not VIDEO_ID_RE.match(video_id):
        abort(404)
    data = read_analysis(video_id)
    if not data:
        return jsonify({"ok": False}), 404
    thumbs = data.get("thumbs")
    if thumbs and not thumbs.get("gray"):
        # Older analyses stored colour thumbnails that the page had to grey out live (slow).
        # Convert the image once, here, instead.
        ffmpeg, _ = find_tool("ffmpeg")
        src, tmp = CACHE / video_id / "thumbs.jpg", CACHE / video_id / "thumbs_gray.jpg"
        try:
            if ffmpeg and src.exists():
                subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-vf", "format=gray", "-q:v", "5", str(tmp)],
                               capture_output=True, timeout=60, creationflags=NO_WINDOW)
                if tmp.exists():
                    tmp.replace(src)
                    thumbs["gray"] = True
                    (CACHE / video_id / "analysis.json").write_text(json.dumps(data), encoding="utf-8")
        except (OSError, subprocess.SubprocessError):
            pass
    return jsonify({"ok": True, "analysis": data, "overrides": read_overrides(video_id)})


# ---------------------------------------------------------------- render

def run_render(job, video_id, edl, name, mode="both"):
    import render

    def progress(pct, message):
        job["progress"] = round(float(pct), 1)
        if not job["log"] or not message.startswith("Encoding frame") or not job["log"][-1]["msg"].startswith("Encoding frame"):
            job_log(job, message)
        else:
            job["log"][-1]["msg"] = message      # keep one moving line instead of hundreds

    try:
        ffmpeg, _ = find_tool("ffmpeg")
        if not ffmpeg and mode != "audio":        # an audio-only export does not need ffmpeg
            raise render.RenderError("ffmpeg is missing. Put ffmpeg.exe in the bin folder.")
        analysis = read_analysis(video_id)
        if not analysis:
            raise render.RenderError("Analyze the video before rendering.")
        result = render.render(edl, analysis, CACHE / video_id, RENDERS, ffmpeg, name, progress, mode=mode)
        job.update(state="done", progress=100.0, result=result)
    except render.RenderError as exc:
        job.update(state="error", error=str(exc))
        job_log(job, "ERROR: " + str(exc))
    except MemoryError:
        job.update(state="error", error="Ran out of memory while rendering. Use fewer bars.")
        job_log(job, "ERROR: " + job["error"])
    except Exception as exc:
        print(f"[render] unexpected error: {exc!r}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        job.update(state="error", error="Render failed unexpectedly. Details are in the console window.")
        job_log(job, "ERROR: " + job["error"])


@app.post("/api/render")
def api_render():
    data = request.get_json(silent=True) or {}
    edl = data.get("edl")
    if not isinstance(edl, dict) or not VIDEO_ID_RE.match(str(edl.get("video") or "")):
        return jsonify({"ok": False, "error": "Nothing to render yet. Press Generate first."}), 400
    video_id = edl["video"]
    mode = data.get("mode") or "both"             # "audio" (WAV), "video" (silent MP4) or "both" (MP4 with the mix)
    if mode not in ("audio", "video", "both"):
        return jsonify({"ok": False, "error": "Unknown export type."}), 400
    with jobs_lock:
        job = render_jobs.get(video_id)
        if job and job["state"] == "running":
            return jsonify({"ok": False, "error": "An export is already running."}), 400
        name = (f"{video_id}_seed{int(edl.get('seed') or 0)}_{time.strftime('%Y%m%d-%H%M%S')}"
                + {"audio": "_audio", "video": "_video", "both": ""}[mode])
        job = {"id": video_id, "state": "running", "progress": 0.0, "log": [], "error": None, "result": None}
        render_jobs[video_id] = job
        threading.Thread(target=run_render, args=(job, video_id, edl, name, mode), daemon=True).start()
    return jsonify({"ok": True})


@app.get("/api/render/job/<video_id>")
def api_render_job(video_id):
    job = render_jobs.get(video_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.get("/renders/<name>")
def render_file(name):
    if not RENDER_NAME_RE.match(name):
        abort(404)
    path = RENDERS / name
    if not path.exists():
        abort(404)
    return send_file(path, conditional=True, max_age=0)


@app.post("/api/slices/<video_id>")
def api_slices(video_id):
    if not VIDEO_ID_RE.match(video_id) or not (CACHE / video_id).is_dir():
        abort(404)
    data = request.get_json(silent=True) or {}
    overrides = data.get("overrides")
    if not isinstance(overrides, dict):
        return jsonify({"ok": False}), 400
    clean = {}
    for key, value in overrides.items():
        if str(key).isdigit() and isinstance(value, dict):
            clean[str(key)] = {"tag": str(value.get("tag") or "")[:8],
                               "locked": bool(value.get("locked")),
                               "deleted": bool(value.get("deleted"))}
    (CACHE / video_id / "slices_user.json").write_text(json.dumps(clean), encoding="utf-8")
    return jsonify({"ok": True})


if __name__ == "__main__":
    for folder in (BIN, CACHE, RENDERS):
        folder.mkdir(exist_ok=True)
    cfg = load_config()
    port = int(cfg.get("port", 5077))
    status = gather_status()
    print("BREAKSHREDDER")
    for name, info in status["tools"].items():
        print(f"  {name:<11} {'OK   ' + str(info['path']) if info['found'] else 'MISSING'}")
    for problem in status["problems"]:
        print("  ! " + problem)
    print(f"\n  Open http://localhost:{port}   (Ctrl+C here to stop)\n")
    if cfg.get("open_browser", True):
        # Open the page in the default browser one second after the server starts.
        import webbrowser
        threading.Timer(1.0, webbrowser.open, args=(f"http://localhost:{port}",)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
