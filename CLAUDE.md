# BREAKSHREDDER

Local tool: YouTube link in, drill'n'bass / breakcore audiovisual re-edit out. Flask server (`app.py`) plus one page (`index.html`), Windows 10, Thorium browser.

**Before doing anything, read `HANDOFF.md` in this folder.** It has the current status, the rules the user set, the edit-list format and the ordered list of what to build next. `BUILD_PROMPT.md` is the original full spec; where they disagree, `HANDOFF.md` wins.

**Adding, changing or swapping an instrument? Read `INSTRUMENTS.md` too.** It lists every place an instrument touches in both files, with step-by-step recipes, and `tests/check_sound.py` checks the result.

Rules that must not be broken (details and reasons are in `HANDOFF.md`):
- UI: three colours only (`#e4e2dc`, `#000`, `#ffe500`; dark mode swaps the first two and uses red `#d60000` instead of yellow), Bahnschrift, 4px black rules. No border-radius, box-shadow, gradients, transitions or emoji. Keep it quiet; no clutter.
- Never load the whole song into the page, and never draw more than one page of slice pads.
- The source audio supplies the music. Bass, reese, acid, drums and melody are ways of processing source slices, chosen automatically. Plain synthesized sound is an optional extra, off by default.
- Renders are clean cuts. Do not re-enable the old flash / RGB-split effects.
- Every sound exists twice with matching maths: live preview in `index.html`, export in `render.py`.
- `index.html` stays a single file.
- One change at a time. Afterwards say plainly what changed, in which files, and how the user tests it. The user is comfortable with computers but is not an advanced programmer; prefers cmd over PowerShell.
- Update `HANDOFF.md` at the end of each session.
