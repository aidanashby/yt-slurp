# Changelog

All notable changes to yt-slurp. Dates are in UK format.

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
