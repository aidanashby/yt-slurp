# yt-slurp: status

Last updated: 13th October 2026

## Where it is

The tool is built and passes its offline tests. It has not yet been run against YouTube, because the build container cannot reach it. The next step is the first live run on Windows: follow "Next" below, step by step.

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

## Next: how to set up and test on Windows

Do these in order. Type or paste each command into PowerShell and press Enter.

### 1. Install the tools (once)

1. Open PowerShell. Press the Windows key, type `PowerShell`, and press Enter.
2. Run each of these, one at a time. Accept any prompts.

   ```powershell
   winget install Python.Python.3.12
   winget install Gyan.FFmpeg
   winget install DenoLand.Deno
   winget install Git.Git
   ```

3. Close PowerShell and open a new window. New programs are only found in new windows.
4. Check that each tool works:

   ```powershell
   py --version
   ffmpeg -version
   deno --version
   git --version
   ```

   `py --version` must show 3.10 or later. If any command says "is not recognized", close the window and open a new one. If it still fails, restart Windows.

### 2. Get the code (once)

```powershell
cd $HOME\Documents
git clone https://github.com/aidanashby/yt-slurp.git
cd yt-slurp
```

The code is now in `Documents\yt-slurp`. To get later updates, run `git pull` inside that folder.

### 3. Create the virtual environment (once)

1. Create it:

   ```powershell
   py -m venv .venv
   ```

2. Turn it on:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   If PowerShell says "running scripts is disabled on this system", run the next command, type `Y` and press Enter, then run the activate command again:

   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

   When the environment is on, the prompt starts with `(.venv)`.

3. Install yt-slurp and its test tools:

   ```powershell
   pip install -e ".[dev]"
   ```

4. Check the install:

   ```powershell
   yt-slurp --help
   python -m pytest
   ```

   The first command lists the options. The second must end with `63 passed`.

### 4. Each time you come back

```powershell
cd $HOME\Documents\yt-slurp
.venv\Scripts\Activate.ps1
```

You can also double-click `yt-slurp.bat` in File Explorer instead. It turns the environment on and shows a menu.

### 5. Smoke test (before any real batch)

This checks that the Whisper app keeps the `[ID]` brackets in filenames.

1. Make the test files:

   ```powershell
   yt-slurp smoke-wav
   ```

   This writes two WAV files to `output\smoke-test\needs-transcription\batch 01\`.
2. Open the Whisper app and add both WAV files from that folder.
3. Transcribe them.
4. For each result, click **Save as .txt**. In the save dialog:
   1. Go to `Documents\yt-slurp\output\smoke-test\whisper-transcripts`.
   2. Check the suggested filename still contains `[AbC-d_123xY] part 01 of 02` (or `part 02 of 02`). Don't change it.
   3. Click Save.
5. Merge the results:

   ```powershell
   yt-slurp merge "output\smoke-test"
   ```

6. Pass: it prints `Merged 1 videos.`, and `output\smoke-test\transcripts\` holds one file containing both parts. Fail: write down exactly how the saved filename differs from the WAV name, and send it to me.

### 6. Live test runs

Use `--limit 5` so each run takes a few minutes. Results go to `output\<channel or playlist name>\`. When a run asks a question, type the answer shown in brackets and press Enter.

1. **Small channel, links only.** Replace `@CHANNEL` with the channel's handle:

   ```powershell
   yt-slurp https://www.youtube.com/@CHANNEL --links-only --limit 5
   ```

   If it asks which types, type `1` for normal videos. Check that `links.txt` lists 5 videos with dates and durations.

2. **Same channel, full run:**

   ```powershell
   yt-slurp https://www.youtube.com/@CHANNEL --limit 5 --update
   ```

   Check these:
   - `transcripts\`: open two files. They should read as clean paragraphs with no repeated lines.
   - `manifest.csv`: open it in Excel. The status column shows what happened to each video.
   - `claude-parts\` and `gemini-notebook\` hold the combined files.

3. **Playlist.** Keep the quotes, because the address contains `?`:

   ```powershell
   yt-slurp "https://www.youtube.com/playlist?list=PLAYLIST_ID" --limit 5
   ```

4. **Long video with no captions** (over 60 minutes). yt-slurp rejects single-video links, so add the video to a playlist of its own (it can be unlisted) and run that playlist:

   ```powershell
   yt-slurp "https://www.youtube.com/playlist?list=PLAYLIST_ID"
   ```

   Check that `needs-transcription\batch 01\` holds two or more WAV parts. Transcribe and save them as in the smoke test, saving into that folder's `whisper-transcripts`. Then run:

   ```powershell
   yt-slurp merge "output\PLAYLIST NAME"
   ```

5. **Non-English video with no English captions.** Use a playlist the same way. In `manifest.csv` the video should show `skipped-non-english`.

6. **Optional, members-only or age-restricted video.** When the run asks about cookies at the end, sign in to YouTube in Firefox first, then type `3` for Firefox.

### 7. What to send me

- The terminal output from any run that went wrong. Select it with the mouse, press Ctrl+C to copy it, and paste it into the chat.
- `manifest.csv` from that run's folder, or just its rows with `failed` in the status column.
- For any transcript that looks wrong, its filename and what is wrong with it.

### 8. If something goes wrong

| What you see | What to do |
|---|---|
| `ffmpeg and ffprobe not found` | Run `winget install Gyan.FFmpeg`, then open a new PowerShell window. |
| A message about a JavaScript runtime | Run `winget install DenoLand.Deno`, then open a new window. |
| `running scripts is disabled` | Run the `Set-ExecutionPolicy` command in step 3. |
| `yt-slurp is not recognized` | The environment is off. Run `.venv\Scripts\Activate.ps1`. |
| Cannot read browser cookies | Close the browser completely (check the system tray), or use Firefox. |
| `confirm you're not a bot` | Wait an hour, then run the same command with `--update`. |
| Rows with `failed` in `manifest.csv` | Copy the text from the error column and send it to me. |

## Possible later work

- Route C: transcribe the WAVs inside yt-slurp with faster-whisper, if the manual saves become tedious. Merge already accepts .txt files from any source.
- Check Google's own Gemini Notebook limits and adjust the constants.
