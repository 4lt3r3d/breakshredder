# BREAKSHREDDER

Paste a YouTube link, get a drill'n'bass / breakcore audiovisual re-edit of it.
Local tool, runs on your own machine at http://localhost:5077

## Setup

1. Run `install.bat` once. It installs the Python packages (Flask, yt-dlp, numpy, scipy, librosa).
2. Have these in the `bin` folder or on PATH: `ffmpeg.exe`, `ffprobe.exe`, and a JavaScript runtime
   (`deno.exe` or Node) for yt-dlp.
3. Run `start.bat`. The page opens in your browser.

Tools are looked for in `bin` first, then PATH, then the paths in `config.json`.

## Use

1. Paste a link and press Fetch (or click a video in the Cache list).
2. Optionally set In and Out, then press Analyze.
3. In Break engine: Play to hear the arrangement, Render MP4 to export it.

## Folders

- `bin\` helper programs
- `cache\<videoID>\` downloaded source, audio, thumbnails, analysis
- `renders\` finished MP4, WAV, edit list and log for each render

## For whoever continues the build

Read `HANDOFF.md` (current state, rules, next steps) and `BUILD_PROMPT.md` (original spec).

## Note

For personal, experimental use. Output made from copyrighted sources is for private use only.
