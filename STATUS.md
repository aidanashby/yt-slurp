# yt-slurp: status

Last updated: 25th November 2026 (0.2.6 release)

## Where it is

yt-slurp 0.2.6 is released as a single self-contained `yt-slurp.exe` on GitHub's Releases page, built and tested on GitHub's Windows machines. It replaces `yt-slurp.bat`, and the repository is public. The `.exe` has been run on the owner's Windows laptop and works, including the first-run downloads on a laptop that had neither tool (0.2.3, HP laptop). Live use on more channels and the Update button (0.2.3 to 0.2.4 is the first real test) are the next things to watch.

## Done

- **`yt-slurp.exe`** (PyInstaller, one file, about 26 MB):
  - Python, Tkinter, yt-dlp and the app built in, so there is nothing to install first; a newer yt-dlp replaces the built-in one by itself (0.2.5);
  - on first run, downloads ffmpeg (from gyan.dev) and Deno (from GitHub) into `%LOCALAPPDATA%\yt-slurp\tools`, checking published checksums, unless copies already exist. Its downloads check certificates against certifi, as yt-dlp does, not the Windows stores (0.2.3: an expired ISRG Root X2 cross-sign in the HP laptop's Windows CA store made gyan.dev fail as "certificate has expired"). ffmpeg took about 13 minutes from gyan.dev there;
  - a "Setting up yt-slurp" window shows these downloads, and updates, step by step with a progress bar, megabytes and time left (0.2.4);
  - checks GitHub for a newer release a few seconds after the window opens, shows a blue **Update** button near the top right, and updates itself with a restart;
  - built and attached to the release by `.github/workflows/build-exe.yml` when a release is published.
- **`yt_slurp_gui.py`** (the window, Tkinter, dark, laid out after Audacity 4 with red and blue highlights, its own slim title bar, and a smile-and-tongue icon):
  - a two-row link box (links as editable blocks, Clear all) with a Slurp split button (the arrow does just normal videos, just Shorts or just live streams), Pause/Resume and Stop, the option to use a file of links, and a list of channels you've done before;
  - one output list for transcripts, WAVs, links and skipped videos, colour-coded, filtered by chips (all on by default) and by a name filter; names are the exact YouTube title, with any extra (part number, skip reason) at the end; the list only follows new items when you're already at the bottom;
  - a file pane that shows transcripts formatted, and becomes a Markdown editor when clicked: find and replace, Undo/Redo (10 steps), Save, Delete; only the tools that apply to the selection are shown, and they wrap in a narrow window;
  - select several results (Shift or Ctrl+click) to see which can be edited, find and replace across all the selected transcripts at once, and save or delete them together;
  - a Play/Stop button for WAV files (Windows);
  - the list grouped by kind (links, transcripts, WAVs, skipped), in the same order as the chips;
  - Delete for any result: files are removed, a deleted link leaves `links.txt`, and none come back on the next slurp;
  - a settings window (the cog at the top right) covering which videos, what to make (transcripts, WAVs, links), caption language, timestamps, WAV options, pace, folders, the transcription app, when to warn about a long run, and advanced limits;
  - buttons for the results and WAV folders, Make Gemini Notebook files, and to launch (or bring forward) the transcription app;
  - a one-line status bar that opens the full log;
  - automatic merging of Whisper text as soon as a video's parts are all saved;
  - a Tools menu (the wrench) with make Gemini Notebook files, open manifest, the log, and (from source) the self-test;
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
- **Tests:** 222 pytest tests (also run on Windows by the build workflow), covering the pure functions, offline end-to-end runs, negative and edge cases, first-run setup and updates, yt-dlp updates and repairs, colour contrast, and the window driving a run, chips, filters, search, the editor, auto-scroll, Pause/Resume, settings and an automatic merge.

- **0.2.5:** yt-dlp updates itself outside the `.exe` (`yt_slurp_engine.py`; `hooks/` bundles the whole standard library so newer versions load); repair and retry during a slurp; single-video links; several links as blocks, sharing one folder; a warning over 500 videos that lists channels; ffmpeg and Deno checked by running them; Try again and Copy details; the dark look.

- **0.2.6:** newest and most viewed limits for long runs (`kept_ids`, stored as `keep` in `run.json`), and time estimates from recent runs (`speed.json` in `%LOCALAPPDATA%\yt-slurp`, transcripts only, no WAVs).

## Decisions taken

- A limit is "the top n overall" each time, so an update only fetches videos that have entered it; earlier ones stay. A channel's videos, Shorts and streams take turns for newest, since listings give no dates.

- Routine yt-dlp updates wait 48 hours after a release; repairs take the newest at once.
- Pasted links covering several channels or playlists share one folder, found again by its set of links (not its name), with the usual question about updating or starting again. Its name is capped at 60 characters, then "and more". Links from a file keep a folder each.
- Single videos go in their channel's folder (`Single videos` only when the channel cannot be read), ignore the minimum length, and always get a transcript.
- A lone video link asks (in the window) about the whole channel or playlist. Among several links, a video link means just that video; from a file or the command line it means the playlist.

- yt-slurp does not run Whisper. Your Whisper transcriber app (local or remote) transcribes the WAVs; you save each result into `whisper-transcripts`, and yt-slurp merges it.
- WAVs all go in one folder, `needs-transcription`. Batch folders were dropped.
- The transcription app keeps yt-slurp's `[ID]` filenames (checked with the smoke test on 14th October, so the menu item was removed; `yt-slurp smoke-wav` remains on the command line).
- Filenames put the title first, then the ID and upload date. Gemini Notebook files are in upload-date order, taken from the manifest.
- Transcripts are Markdown (`.md`) with the details as a heading and list at the top.
- Slurps output transcripts only. Bundling is a separate step, for Gemini Notebook only: Claude and ChatGPT projects take the per-video transcripts as they are.
- Skipped videos show in the window with the reason: shorter than the minimum, not in English with no captions, private or deleted, live stream not finished, or turned off in settings.
- Audio over 60 minutes is split into equal parts no longer than the limit, each cut at the nearest silence within two minutes.
- "Start again" keeps `whisper-transcripts`.
- Auto-captions are used only in the video's original language; machine translations are ignored.
- Gemini defaults: 50 sources and 400,000 words per source, inside Gemini Notebook's limits of 50 sources (free plan) and 500,000 words per source.
- Signed-in videos use browser cookies only for the retry at the end of a run.
- Closing a question dialog picks the cautious answer: keep what exists, or don't use a browser.

## Not yet tested

- 0.2.6: the long-run window by hand in the `.exe`, and a limited run of several large channels. Checked live from source: 3 newest and 4 most viewed from one channel.
- 0.2.5: a full slurp in the `.exe`, the first-run downloads, the `.exe` updating yt-dlp itself, and Windows 10. Windows misplaces a DPI-unaware window snapped to the inner edge of a second screen with different scaling (any Tk window, 150% beside 100%); `TitleBar.fix_snap` corrects it after the drag, leaving a 7-pixel gap at that edge, and the owner has confirmed it. Checked by the owner: snapping, top-edge resizing, and the minimise and restore animation. Checked live from source: a mid-run yt-dlp repair, a video with its own channel, and combined folders.
- The Update button end to end, from 0.2.3 to 0.2.4.
- The "Setting up yt-slurp" window in the `.exe`. It is tested from source; the 0.2.3 to 0.2.4 update is the first chance to see it in a build.
- When running tests on Windows, put `%LOCALAPPDATA%\yt-slurp\tools` on PATH first, or the 24 tests that need ffmpeg are skipped. The editor test `test_edit_save_replace_undo` timed out once in a full run on 24th October 2026 and passed on reruns; watch for it recurring.
- Reading browser cookies for members-only or age-restricted videos.

## Making a release

1. Bump `__version__` in `yt_slurp.py` and add a section to `CHANGELOG.md`; commit and push.
2. On GitHub, go to **Releases**, then **Draft a new release**. Create the tag (for example `v0.2.1`) on publish, set the title, paste the changelog section, and select **Publish release**.
3. The workflow builds `yt-slurp.exe` and attaches it to the release in a few minutes. Running copies then show the Update button.

## Next: using it

### 1. Set up the window once

1. Click the cog at the top right. Under **Transcription app**, click **Choose the transcription app...** and pick the file you use to start it (its .exe, .bat, .py or shortcut; this is your transcription app, not yt-slurp).
2. Check **Word in its window title** matches a word in the app's title bar (left blank, the app's filename is used). yt-slurp uses this to bring the app forward instead of starting a second copy. Click **Save**.
3. Tools menu (the wrench), **Run the self-test**. It should say "Self-test passed".

### 2. Live tests

In Settings, tick **Test run: only do the first few videos** (5 is fine) for these.

1. **A small channel.** Paste its link (for example `https://www.youtube.com/@SomeChannel`) and click **Slurp**. Answer the question about which kinds of video. Watch results appear in the list on the left, colour-coded; click one to read it on the right. Click the chips above the list to hide or show links, transcripts, WAVs or skipped videos. Try **Pause** and **Resume**.
2. **A playlist.** Paste the playlist link and click **Slurp**.
3. **A long video with no captions** (over 60 minutes). Paste its link and choose **Just this video**. There should be two or more WAV parts in the list (blue). Click **Open WAV folder** and **Launch transcription app**, transcribe the parts, and save each into `whisper-transcripts`. When all parts are saved, the merged transcript appears in the list by itself.
4. **A non-English video with no English captions**, the same way. It should appear under Skipped with the reason "not in English, no captions".
5. **Optional: a members-only or age-restricted video.** At the end of the run, yt-slurp asks which browser to use. Sign in to YouTube in Firefox first, then choose Firefox.

### 3. What to send Claude

- Anything that looked wrong, and the log (select **Show log** at the bottom, then **Copy all**).
- If the window shows "Something went wrong", the file it names (`error.log`).
- For a failed video: Tools (the wrench), **Open the manifest in Excel**, and copy its row.

### 4. If something goes wrong

| What you see | What to do |
|---|---|
| A message with **Copy details** | Select **Copy details** and send it to Claude. |
| Double-clicking does nothing visible | yt-slurp may already be open behind other windows. Check the taskbar. |
| ffmpeg or Deno missing | Slurp again: yt-slurp downloads it. |
| Cannot read browser cookies | Close the browser completely (check the system tray), or choose Firefox. |
| YouTube asks to confirm you are not a bot | Wait an hour, then Slurp the same link again. |
| Videos counted as failed | Tools, Open the manifest in Excel, and send Claude the error column. |
