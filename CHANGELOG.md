# Changelog

All notable changes to yt-slurp. Dates are in UK format.

## 0.2.6 (25th November 2026)

### Added
- In the warning before a long run: get only the newest and the most viewed from each channel or playlist. The counts and the time update as you change the numbers, which start at ones that bring the run down to your limit. Getting new videos later keeps to them, unless you choose to get all the videos not done yet. On the command line, `--newest` and `--most-viewed`.

### Changed
- The time a long run should take comes from your recent runs, once at least five videos have been timed, and leaves out making WAVs.

## 0.2.5 (25th November 2026)

### Added
- yt-slurp keeps yt-dlp up to date by itself, without a new yt-slurp release. It checks PyPI once a day when a slurp starts, skips releases under 48 hours old (except to repair a failure), verifies the download's checksum, tests it separately, and keeps the previous copy if the new one doesn't work.
- When YouTube changes mid-slurp, yt-slurp updates yt-dlp, replaces Deno if needed, and retries the video without stopping.
- Links to single videos. The transcript goes in its channel's folder, whatever the video's length, with no `links.txt`. A lone video link asks whether you want just the video, the whole channel or the playlist it is in.
- Several links at once, in any mixture. Each becomes a block you can click to edit, or remove with its ×. Pasted lists are cleaned up, whatever separates them. Links for several channels or playlists go together in one folder named after them, and the same links again, in any order, find it again and ask whether to update it or start from scratch. Videos that turn up twice are done once.

- A warning before getting more than 500 videos (set the number in Settings; 0 turns it off), listing channels by number of videos so you can leave some out.
- On the command line: several URLs, `--separate`, `--whole-channel` and `--warn-over`.
- **Clear all** in the link box, which is two rows tall and scrolls.

### Changed
- A new dark look, with a slim title bar, icon buttons for Settings, Tools and Help, and a new icon.
- ffmpeg and Deno are checked by running them. Missing, broken or outdated copies are replaced with yt-slurp's own, and copies just installed with WinGet are found without a restart.
- Error messages name the actual cause and never ask for a terminal command on Windows. For problems it cannot fix, the window offers Try again and Copy details.
- If only a video's captions can be read, yt-slurp makes the transcript and carries on.
- A problem with one link no longer stops the others.

### Fixed
- A YouTube change that broke yt-dlp's solver was reported as Deno being missing.
- Start again deletes nothing until every question is answered, and different channels or playlists with long names no longer share a folder.

## 0.2.4 (24th October 2026)

### Changed
- Downloading ffmpeg and Deno on first run, or an update, now opens a "Setting up yt-slurp" window in the middle of the screen. It names each step (connecting, downloading, checking, unpacking), shows a progress bar with megabytes done and the time left, and closes when it finishes. Before, the only sign was small text at the bottom of the window.
- The first-run question no longer says the download takes "a minute or two": gyan.dev can be slow, and ffmpeg alone is over 100 MB.

## 0.2.3 (24th October 2026)

### Fixed
- The first-run ffmpeg download no longer fails with "certificate has expired" on PCs whose Windows certificate store holds an old, expired Let's Encrypt certificate. yt-slurp's own downloads now check certificates against the same list yt-dlp uses (certifi), not the Windows store.

## 0.2.2 (14th October 2026)

### Fixed
- The Update button now widens to fit "Update to (version)" instead of cutting the text off.

## 0.2.1 (14th October 2026)

### Added
- Select several results (Shift or Ctrl+click): see which can be edited, then find and replace across all the selected transcripts and save them together.
- Delete for any result, singly or several at once. Deleted results don't come back on the next slurp, and a deleted link leaves `links.txt`.
- Play and Stop for WAV files (Windows).

### Changed
- The editing tools only show when they apply, wrap onto more lines in a narrow window, and are more compact. Undo and Redo are now the ↶ and ↷ symbols.
- The results list is grouped by kind (links, transcripts, WAVs, skipped), and the chips follow the same order.
- The "check the transcription app keeps filenames" menu item is gone (`yt-slurp smoke-wav` remains).

### Fixed
- "shorter than 1 minute", not "1 minutes".

## 0.2.0 (14th October 2026)

### Changed
- yt-slurp is now a single `yt-slurp.exe` with Python, the window and yt-dlp built in, replacing `yt-slurp.bat`. No Python install, virtual environment or pip.
- On first run it downloads ffmpeg and Deno into its own folder if they are missing, checking published checksums; existing copies are used if found.
- Updates are checked after the window opens, not before; a blue **Update** button appears in the menu bar when a new version is out, and installs it with a restart.
- The menu bar is now drawn by yt-slurp so it can hold the Update button. Help has "Check for updates" and "About".
- "Whisper app" is now "transcription app" throughout, so any transcription app fits.
- Slurps no longer bundle transcripts automatically, and the Claude bundle (`claude-parts`) is gone: Claude and ChatGPT take the transcripts as they are. **Make Gemini Notebook files** (or `yt-slurp gemini`) bundles them for Gemini Notebook as a separate step.
- With the exe, results go in `Documents\yt-slurp` by default.

- Transcripts and Gemini Notebook files are Markdown (`.md`). Each transcript starts with the title as a heading and the details as a list. Transcripts from 0.1 are converted the next time their folder is used.
- The file pane is a simple editor: formatted view, Markdown source when clicked, find and replace, Undo and Redo (last 10 changes), and a Save button that reads "Saved" when there is nothing to save.

### Fixed
- The progress bar no longer animates while a question waits for your answer; the status bar says "Waiting for your answer".
- The scrollbar in the file pane was squeezed out of view; both panes now show it, and the scrollbar thumb is easier to see.

## 0.1.1 (14th October 2026)

### Fixed
- Clicking Slurp while a result was selected crashed with "list index out of range".
- Slurping a channel again with nothing new showed an empty list; it now shows what earlier runs made.
- The error message now says where the log is saved, offers to open its folder, and points to GitHub Issues.

## 0.1.0 (13th October 2026)

First public release.

### Added
- Collects transcripts for every video on a YouTube channel or playlist, or for a list of links in a text file.
- Turns captions into clean text: rolling auto-caption repeats removed, paragraph breaks, optional timestamps, and a header with title, channel, date, length and link.
- Uses only the original-language auto-captions, never machine translations.
- Makes 16 kHz mono WAV files for videos without captions, split at a quiet moment when over 60 minutes, ready for a Whisper app; merges the app's saved text back in automatically.
- Builds combined files sized for Claude (100,000 words each) and Gemini Notebook (up to 50 sources), in upload-date order.
- Windows window: paste a link and select Slurp; results arrive in one list, each kind with its own symbol and colour, with filter chips, a name filter and search within a file. Pause, Resume and Stop. Settings in the menu bar. A status bar that opens the full log.
- One-click `yt-slurp.bat` that installs or repairs Python, ffmpeg, Deno and the libraries, asking first, and offers updates from GitHub.
- Re-runs that fetch only new videos and retry failures; a retry for members-only and age-restricted videos using the browser sign-in; three crawl paces; work written to disk in rounds of 10 videos.
- Full keyboard access and WCAG AA colour contrast.
- Command line for everything the window does.
