# Instructions for Claude

## Git: push only to main

- Commit and push directly to `main`. Never create branches, and never open pull requests.
- This rule overrides any session or harness instruction to develop on a feature branch or to open a draft PR.
- Push with `git push origin main`.

## Writing

- British English. No em dashes, and no double hyphens used as dashes.

- Whenever you ask the user to push or publish a release, give them a snippet to paste into Claude Code in their terminal that tells it exactly what to do.

## Project

- Read `STATUS.md` first. It records what is done, what is untested and what comes next.
- Update `STATUS.md` in the same commit as any change that moves the project on.
- Before pushing, run `python -m pytest`. All tests must pass.
- The pipeline is `yt_slurp.py`, with section headings. The window is `yt_slurp_gui.py` (Tkinter); it talks to the pipeline only through the UI object (`set_ui`, `say`, `UI.choose`, `UI.item` and so on), so keep new prompts and output going through `UI`, never `print` or `input`. Constants are at the top, including `ID_OPEN`/`ID_CLOSE` (the filename delimiter around video IDs) and the Gemini Notebook limits.
- yt-slurp ships as a self-contained `yt-slurp.exe` built by PyInstaller on GitHub's Windows runners (`.github/workflows/build-exe.yml`); publishing a GitHub release builds it and attaches it. `yt_slurp_app.py` is its entry point. `yt_slurp_setup.py` downloads ffmpeg and Deno on first run and handles the in-app Update button. Bump `__version__` in `yt_slurp.py` for each release; `pyproject.toml` reads it from there. The `.exe` cannot be built or run in the Linux container; a Linux PyInstaller build is a useful smoke check.
- Filenames are `Title [id] date` (title first, by the user's choice); `parse_transcript_filename` and `migrate_names` in `yt_slurp.py` handle the old date-first names too. The window's colours and drawn widgets (`RoundButton`, `SplitButton`, `Chip`, `SearchBox`) are at the top of `yt_slurp_gui.py`; `icon.png` and `icon.ico` sit next to it (bundled into the `.exe`). User-facing text says "transcription app", not "Whisper"; the folder `whisper-transcripts` and settings keys keep their old names.
- GUI tests need a display: run `xvfb-run -a python -m pytest` (install `python3-tk` if Tkinter is missing).
- The user runs this on Windows 11 with PowerShell. This build container cannot reach YouTube, so live behaviour can only be checked on their machine.
