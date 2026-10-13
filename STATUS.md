# yt-slurp: status

Last updated: 13th October 2026

## Where it is

yt-slurp now has a window and a one-click installer. Double-click `yt-slurp.bat`: it sets up whatever is missing and opens the window. Everything passes its offline tests, including the window driving a full run, but nothing has yet run against YouTube or on Windows, because the build container can reach neither. The next step is the first run on your laptop: follow "Next" below.

## Done

- **`yt-slurp.bat`** (installer and launcher):
  - if the window is already open, brings it to the front instead of opening a second one;
  - offers to update from GitHub when a newer version exists, and never updates if files have been edited locally;
  - finds a Python from 3.10 up with Tkinter, preferring 3.10 to 3.13 (on your laptop, 3.11), and offers to install Python 3.12 only if none is suitable;
  - finds ffmpeg and Deno on the PATH or in their usual install folders, offering winget installs only when they are missing;
  - creates the `.venv` environment, and repairs it if broken;
  - installs the libraries only when they have changed, and updates yt-dlp weekly;
  - opens the window with no console left behind.
- **`yt_slurp_gui.py`** (the window, Tkinter):
  - a link box with Slurp and Stop buttons, the option to use a file of links, and a list of channels you've done before;
  - plain-English settings on the left, saved between sessions;
  - an output panel that shows transcripts, WAV files or links as they are made, with a preview of the selected file;
  - progress bar, status counts and messages;
  - buttons for the results, WAV, Claude and Gemini folders, and to launch (or bring forward) the Whisper app;
  - questions as pop-up dialogs;
  - automatic merging of Whisper text as soon as a video's parts are all saved;
  - a Tools menu with the filename smoke test, merge now, open manifest and self-test.
- **`yt_slurp.py`** (the pipeline):
  - channel and playlist listing, duration filter, `links.txt` and `manifest.csv`;
  - captions to clean text;
  - WAVs for videos without captions, split at silence, in batch folders;
  - merge, and the Claude and Gemini Notebook combined files;
  - update and fresh re-runs, cookie retry, bot-check pause, a run lock per folder, and a clean stop.
  The command line (`yt-slurp ...`) still works.
- **Tests:** 66 pytest tests, covering the pure functions, an offline end-to-end run, and the window driving a run and an automatic merge.

## Decisions taken

- yt-slurp does not run Whisper. Your Whisper transcriber app (local or remote) transcribes the WAVs; you save each result into `whisper-transcripts`, and yt-slurp merges it.
- WAVs go in batch folders of 10, because the app loses unsaved results when it closes.
- Audio over 60 minutes is split into equal parts no longer than the limit, each cut at the nearest silence within two minutes.
- "Start again" keeps `whisper-transcripts`.
- Auto-captions are used only in the video's original language; machine translations are ignored.
- Gemini defaults: 50 sources and 400,000 words per source. Third-party guides give a limit of 500,000 words; Google's own page was not checked.
- Signed-in videos use browser cookies only for the retry at the end of a run.
- Closing a question dialog picks the cautious answer: keep what exists, or don't use a browser.

## Not yet tested (needs your laptop)

- `yt-slurp.bat` itself. It is written for Windows `cmd` and cannot run in the build container.
- Any live YouTube request.
- Whether the Whisper app's save dialog keeps the `[ID]` brackets (use the smoke test before any real batch).
- Reading browser cookies, and the Launch Whisper app button.

## Next: first run on your laptop

### 1. Get the new version (this once only)

Your copy of the repo predates the installer, so get it once by hand. Open PowerShell (press the Windows key, type `PowerShell`, press Enter), then paste:

```powershell
cd <the folder you cloned yt-slurp into>
git pull
```

After this, `yt-slurp.bat` checks for updates itself.

### 2. Double-click `yt-slurp.bat`

Open the folder you cloned yt-slurp into in File Explorer and double-click `yt-slurp.bat`. On your laptop you should see, in order:

1. "Python: C:\Program Files\Python311\python.exe" (or another 3.10 to 3.13), then "Creating the environment".
2. "ffmpeg: found."
3. "Deno was not found ... Install Deno with winget? [Y/N]". Press `Y`. It installs, then says "Deno: found."
4. "Installing yt-slurp and its libraries". This takes a minute or two the first time.
5. "Opening the yt-slurp window...", and the window opens. A "How to use yt-slurp" message appears the first time.

If a stage stops with a message instead, copy the whole black window's text (right-click the title bar, Edit, Select All, then Enter) and send it to Claude.

Next time, double-clicking just opens the window within a few seconds.

### 3. Set up the window once

1. Under **Whisper app** on the left, click **Choose the Whisper app...** and pick the file you use to start it (its .exe, .bat, .py or shortcut).
2. Check **Its window title contains** matches a word in the Whisper app's title bar (default `Whisper`). yt-slurp uses this to bring the app forward instead of starting a second copy.
3. Tools menu, **Run the self-test**. It should say "Self-test passed".

### 4. Smoke test (before any real batch)

1. Tools menu, **Check the Whisper app keeps filenames**. Two short test WAVs are made and their folder opens.
2. Click **Launch Whisper app**, and drag both WAVs into it. Transcribe them.
3. Click **Save as .txt** for each, and save into the `whisper-transcripts` folder the message names. Keep the suggested name.
4. Within a few seconds yt-slurp says **Test passed**. If nothing happens, the app changed the filenames: send Claude the saved names.

### 5. Live tests

In the settings, tick **Test run: only do the first few videos** (5 is fine) for these.

1. **A small channel.** Paste its link (for example `https://www.youtube.com/@SomeChannel`) and click **Slurp**. Answer the question about which kinds of video. Watch transcripts appear on the right; click one to read it. Choose **Links** above the list to see the links.
2. **A playlist.** Paste the playlist link and click **Slurp**.
3. **A long video with no captions** (over 60 minutes). yt-slurp works on channels and playlists, so put the video in a playlist of its own (it can be unlisted) and slurp that. Choose **WAV files** above the list; there should be two or more parts. Click **Open WAV folder** and **Launch Whisper app**, transcribe the parts, and save each into `whisper-transcripts`. When all parts are saved, the merged transcript appears under Transcripts by itself.
4. **A non-English video with no English captions**, in a playlist the same way. It should be counted as skipped.
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
| A message about a JavaScript runtime | Double-click `yt-slurp.bat` again; it offers to install Deno. |
| Cannot read browser cookies | Close the browser completely (check the system tray), or choose Firefox. |
| YouTube asks to confirm you are not a bot | Wait an hour, then Slurp the same link again. |
| Videos counted as failed | Tools, Open the manifest in Excel, and send Claude the error column. |

## Possible later work

- Check Google's own Gemini Notebook limits and adjust the constants.
