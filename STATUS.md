# yt-slurp: status

Last updated: 12th October 2026

## Where it is

The tool is built and passes its offline tests. It has not yet been run against YouTube, because the build container cannot reach it. The next step is the first live run on Windows.

## Done

- Full pipeline in `yt_slurp.py`:
  - channel and playlist listing, with the type prompt and `--file` input;
  - duration filter, metadata pass, `links.txt` and `manifest.csv`;
  - captions to clean text (rolling duplicates removed, paragraph breaks, optional timestamps, header on each file);
  - WAVs for videos without captions: 16 kHz mono 16-bit PCM, split at silence, in batch folders;
  - `merge` for the Whisper app's .txt files;
  - Claude and Gemini Notebook combined files;
  - update and fresh re-runs, the cookie retry for sign-in videos, the bot-check pause, the JavaScript runtime and ffmpeg checks, and Ctrl+C handling;
  - the `smoke-wav` command.
- `pyproject.toml` (`pip install -e .` gives the `yt-slurp` command), `yt-slurp.bat` launcher menu, README.
- 63 pytest tests: pure functions, plus an offline end-to-end run with a fake network layer and real ffmpeg.

## Decisions taken

- Transcript route A: the user drags WAVs into the Whisper app and clicks Save as .txt into `whisper-transcripts\`. The app is unchanged.
- WAVs go in batch folders of 10 (`--batch-files`), because the app loses unsaved results when it closes.
- Audio over 60 minutes is split into equal parts no longer than the limit, each cut at the nearest silence within two minutes.
- `--fresh` keeps `whisper-transcripts\`.
- Auto-captions are used only in the video's original language. Machine translations are ignored.
- Gemini defaults: 50 sources and 400,000 words per source. Third-party guides give a limit of 500,000 words; Google's own page was not checked.
- Statuses beyond the specification: `skipped-private` and `pending`.
- `--cookies-from-browser` is used only for the end-of-run retry, so the main pass runs without cookies.

## Not yet tested (needs the user's Windows machine)

- Any live YouTube request: listing, metadata, captions, audio download.
- Whether the Whisper app's save dialog keeps the `[ID]` brackets. Run `yt-slurp smoke-wav` before any real batch.
- Reading browser cookies, the bot-check pause, and the JavaScript runtime message.
- `yt-slurp.bat` on Windows.

## Next

1. Set up the venv, install ffmpeg and Deno, and run `yt-slurp smoke-wav`. Send its result.
2. Live runs with `--limit 5` on these inputs:
   - a small channel;
   - a playlist;
   - a video over 60 minutes with no captions;
   - a non-English video with no English captions;
   - optionally, a members-only or age-restricted video.
3. Fix whatever the live runs show, then run a full channel end to end.

## Possible later work

- Route C: transcribe the WAVs inside yt-slurp with faster-whisper, if the manual saves become tedious. Merge already accepts .txt files from any source.
- Check Google's own Gemini Notebook limits and adjust the constants.
