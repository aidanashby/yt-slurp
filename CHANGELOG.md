# Changelog

All notable changes to yt-slurp. Dates are in UK format.

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
