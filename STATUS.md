# yt-slurp: status

Last updated: 13th October 2026 (pre-release review)

## Where it is

yt-slurp is now a single self-contained `yt-slurp.exe`, built on GitHub's Windows machines and attached to each release. It replaces `yt-slurp.bat`. The window, pipeline and first-run setup pass their offline tests here, and a Linux build of the bundle starts cleanly. The Windows `.exe` itself is built and smoke-started by the GitHub workflow, but it has not yet been tried on a real desktop, and live YouTube requests are still untested. Next: publish release v0.2.0 and try it (see "Next" below).

## Done

- **`yt-slurp.exe`** (PyInstaller, one file, about 26 MB):
  - Python, Tkinter, yt-dlp and the app built in, so there is nothing to install first;
  - on first run, downloads ffmpeg (from gyan.dev) and Deno (from GitHub) into `%LOCALAPPDATA%\yt-slurp\tools`, checking published checksums, unless copies already exist;
  - checks GitHub for a newer release a few seconds after the window opens, shows a blue **Update** button in the menu bar, and updates itself with a restart;
  - built and attached to the release by `.github/workflows/build-exe.yml` when a release is published.
- **`yt_slurp_gui.py`** (the window, Tkinter, styled after the Whisper Transcriber app, with a red tongue icon):
  - a link box with a Slurp split button (the arrow does just normal videos, just Shorts or just live streams), Pause/Resume and Stop, the option to use a file of links, and a list of channels you've done before;
  - one output list for transcripts, WAVs, links and skipped videos, colour-coded, filtered by chips (all on by default) and by a name filter; names are the exact YouTube title, with any extra (part number, skip reason) at the end; the list only follows new items when you're already at the bottom;
  - a file pane that shows transcripts formatted, and becomes a Markdown editor when clicked: find and replace, Undo/Redo (10 steps), Save;
  - a settings window (Settings in the menu bar) covering which videos, what to make (transcripts, WAVs, links), caption language, timestamps, WAV options, pace, folders, the transcription app and advanced limits;
  - buttons for the results and WAV folders, Make Gemini Notebook files, and to launch (or bring forward) the transcription app;
  - a one-line status bar that opens the full log;
  - automatic merging of Whisper text as soon as a video's parts are all saved;
  - a Tools menu with settings, the filename smoke test, make Gemini Notebook files, open manifest, the log, and the self-test.
- **`yt_slurp.py`** (the pipeline):
  - channel and playlist listing, duration filter, `links.txt` (URLs only) and `manifest.csv`;
  - work in rounds of 10 videos, rewriting links and the combined files after each round;
  - title-first filenames (`Title [id] date`), with older date-first folders renamed on the next run;
  - captions to clean text;
  - WAVs for videos without captions, split at silence, all in `needs-transcription`;
  - options to leave out transcripts, WAVs or links, and three crawl paces;
  - merge, and a separate step that bundles transcripts for Gemini Notebook (`yt-slurp gemini`);
  - update and fresh re-runs, cookie retry, bot-check pause, a run lock per folder, and a clean stop.
  The command line (`yt-slurp ...`) still works.
- **Pre-release review** (see `docs/TEST-REPORT.md`): keyboard access and WCAG AA contrast throughout the window, a symbol as well as a colour for each kind of result, video IDs validated before use in any path, damaged settings files tolerated, and a fix for very slow search highlighting in long transcripts.
- **Tests:** 108 pytest tests, covering the pure functions, offline end-to-end runs, negative and edge cases, and the window driving a run, chips, filters, search, auto-scroll, Pause/Resume, settings and an automatic merge.

## Decisions taken

- yt-slurp does not run Whisper. Your Whisper transcriber app (local or remote) transcribes the WAVs; you save each result into `whisper-transcripts`, and yt-slurp merges it.
- WAVs all go in one folder, `needs-transcription`. Batch folders were dropped.
- Filenames put the title first, then the ID and upload date. Gemini Notebook files are in upload-date order, taken from the manifest.
- Transcripts are Markdown (`.md`) with the details as a heading and list at the top.
- Slurps output transcripts only. Bundling is a separate step, for Gemini Notebook only: Claude and ChatGPT projects take the per-video transcripts as they are.
- Skipped videos show in the window with the reason: shorter than the minimum, not in English with no captions, private or deleted, live stream not finished, or turned off in settings.
- Audio over 60 minutes is split into equal parts no longer than the limit, each cut at the nearest silence within two minutes.
- "Start again" keeps `whisper-transcripts`.
- Auto-captions are used only in the video's original language; machine translations are ignored.
- Gemini defaults: 50 sources and 400,000 words per source. Third-party guides give a limit of 500,000 words; Google's own page was not checked.
- Signed-in videos use browser cookies only for the retry at the end of a run.
- Closing a question dialog picks the cautious answer: keep what exists, or don't use a browser.

## Not yet tested (needs your laptop)

- `yt-slurp.exe` on a real Windows desktop: first-run downloads, the Update button, the SmartScreen prompt.
- Any live YouTube request.
- Whether your transcription app's save dialog keeps the `[ID]` brackets (use the smoke test before the first real WAVs).
- Reading browser cookies, and the Launch transcription app button.

## Next: first run of the .exe

### 1. Publish the release

On GitHub, go to **Releases**, then **Draft a new release**. Type the tag `v0.2.0`, choose **Create new tag: v0.2.0 on publish**, set the title to `yt-slurp 0.2.0`, paste the 0.2.0 notes from `CHANGELOG.md`, and select **Publish release**. About five minutes later, the build attaches `yt-slurp.exe` to the release (watch it under **Actions**).

### 2. Download and run it

1. Download `yt-slurp.exe` from the release, and move it somewhere you'll keep it.
2. Double-click it. If "Windows protected your PC" appears, select **More info**, then **Run anyway**.
3. If ffmpeg or Deno is missing, yt-slurp offers to download them. Select **Yes**.
4. Your settings from the old version carry over, including your results folder.
5. The old repository folder with `.venv` is no longer needed to run yt-slurp.

### 3. Set up the window once

1. Click **Settings** in the menu bar. Under **Transcription app**, click **Choose the transcription app...** and pick the file you use to start it (its .exe, .bat, .py or shortcut).
2. Check **Word in its window title** matches a word in the app's title bar (left blank, the app's filename is used). yt-slurp uses this to bring the app forward instead of starting a second copy. Click **Save**.
3. Tools menu, **Run the self-test**. It should say "Self-test passed".

### 4. Smoke test (before the first real WAVs)

1. Tools menu, **Check the transcription app keeps filenames**. Two short test WAVs are made and their folder opens.
2. Click **Launch transcription app**, and drag both WAVs into it. Transcribe them.
3. Click **Save as .txt** for each, and save into the `whisper-transcripts` folder the message names. Keep the suggested name.
4. Within a few seconds yt-slurp says **Test passed**. If nothing happens, the app changed the filenames: send Claude the saved names.

### 5. Live tests

In Settings, tick **Test run: only do the first few videos** (5 is fine) for these.

1. **A small channel.** Paste its link (for example `https://www.youtube.com/@SomeChannel`) and click **Slurp**. Answer the question about which kinds of video. Watch results appear in the list on the left, colour-coded; click one to read it on the right. Click the chips above the list to hide or show links, skipped videos, transcripts or WAVs. Try **Pause** and **Resume**.
2. **A playlist.** Paste the playlist link and click **Slurp**.
3. **A long video with no captions** (over 60 minutes). yt-slurp works on channels and playlists, so put the video in a playlist of its own (it can be unlisted) and slurp that. There should be two or more WAV parts in the list (blue). Click **Open WAV folder** and **Launch transcription app**, transcribe the parts, and save each into `whisper-transcripts`. When all parts are saved, the merged transcript appears in the list by itself.
4. **A non-English video with no English captions**, in a playlist the same way. It should appear under Skipped with the reason "not in English, no captions".
5. **Optional: a members-only or age-restricted video.** At the end of the run, yt-slurp asks which browser to use. Sign in to YouTube in Firefox first, then choose Firefox.

### 6. What to send Claude

- Anything that looked wrong, and the messages in the box at the bottom of the window (click in it, press Ctrl+A, then Ctrl+C).
- If the window shows "Something went wrong", the file it names (`error.log`).
- For a failed video: Tools, **Open the manifest in Excel**, and copy its row.

### 7. If something goes wrong

| What you see | What to do |
|---|---|
| The black window stops with a message | Copy its text and send it to Claude. |
| Double-clicking does nothing visible | yt-slurp may already be open behind other windows. Check the taskbar. |
| "No Python 3.10 or later with Tkinter" | Press `Y` to install Python 3.12, or install Python from python.org with "tcl/tk and IDLE" ticked. |
| ffmpeg or Deno missing | Restart yt-slurp and select Yes when it offers to download them. |
| Cannot read browser cookies | Close the browser completely (check the system tray), or choose Firefox. |
| YouTube asks to confirm you are not a bot | Wait an hour, then Slurp the same link again. |
| Videos counted as failed | Tools, Open the manifest in Excel, and send Claude the error column. |

## Possible later work

- Check Google's own Gemini Notebook limits and adjust the constants.
