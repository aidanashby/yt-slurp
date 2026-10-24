# Changelog

All notable changes to yt-slurp. Dates are in UK format.

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
