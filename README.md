# yt-slurp

yt-slurp collects the transcripts of every video on a YouTube channel or playlist, so you can give them to an AI assistant such as Claude or Gemini Notebook (formerly NotebookLM) for research and analysis. Paste a link and click **Slurp**:
- Videos with captions become clean, readable text files, each headed with the title, channel, date, length and link.
- Videos without captions become audio files, ready for a transcription app such as one based on Whisper.
- Add the transcripts to Claude or ChatGPT as they are. For Gemini Notebook, which limits how many sources a notebook can hold, one click bundles them into files that fit.

It runs on Windows 10 and 11, and works on your own computer. It has no account, server or subscription.

![The yt-slurp window. A channel link is in the box at the top beside a green Slurp button. On the left is a list of results, each marked with a symbol: a square for transcripts, a musical note for audio files, an arrow for links and a crossed circle for skipped videos, with chips above the list to show or hide each kind. On the right, the selected transcript is shown formatted, with its title as a heading and its details in bold, and the editing tools above it.](docs/screenshot.png)

## Contents

- [What you need](#what-you-need)
- [Install and first run](#install-and-first-run)
- [Using yt-slurp](#using-yt-slurp)
- [Videos without captions](#videos-without-captions)
- [What you get](#what-you-get)
- [Settings](#settings)
- [Troubleshooting](#troubleshooting)
- [Privacy and responsible use](#privacy-and-responsible-use)
- [Command line](#command-line)
- [For developers](#for-developers)
- [Licence](#licence)

## What you need

- Windows 10 or Windows 11.
- An internet connection.
- For videos without captions only: a transcription app (for example, one based on OpenAI's Whisper) that saves its results as `.txt` files, one per audio file.

You don't need to install anything else. yt-slurp is a single program with everything it needs built in, apart from two free tools, ffmpeg and Deno, which it downloads for you on first run.

## Install and first run

1. Go to the [latest release](https://github.com/aidanashby/yt-slurp/releases/latest) and download **`yt-slurp.exe`**.
2. Move it somewhere you'll keep it, such as your Desktop or a `yt-slurp` folder in Documents.
3. Double-click **`yt-slurp.exe`**.
4. The first time, Windows may show **"Windows protected your PC"**. This appears for any new program that isn't signed with a paid certificate. Select **More info**, then **Run anyway**.
5. yt-slurp opens and checks for ffmpeg, which makes audio files, and Deno, which yt-dlp needs to read YouTube. If either is missing, it asks to download them. Select **Yes**: a window shows the progress. It happens once (it can take 15 minutes or more on a slow connection), needs no admin rights, and puts them in yt-slurp's own folder (`%LOCALAPPDATA%\yt-slurp\tools`). If you already have them installed, yt-slurp uses those.
6. A short "How to use yt-slurp" guide appears. You're ready.

After that, double-clicking `yt-slurp.exe` opens the window in a few seconds. If yt-slurp is already open, it brings that window to the front instead of opening a second one.

**Updates.** A few seconds after yt-slurp starts, it checks GitHub for a newer version. If there is one, a blue **Update** button appears at the right of the menu bar. Select it to download the new version and restart; your settings and results are kept. You can also check by hand: select **Help**, then **Check for updates**.

**Where your results go.** By default, results go in `Documents\yt-slurp`. To change this, go to **Settings**, then **Where things go**.

## Using yt-slurp

1. Copy the address of a YouTube **channel** (for example `https://www.youtube.com/@SomeChannel`) or **playlist** (an address containing `playlist?list=`).
2. Paste it into the box at the top of the window.
3. Select **Slurp**. To fetch only one kind of video, select the arrow on the right of the Slurp button and choose **Just normal videos**, **Just Shorts** or **Just live streams**.
4. Answer any questions that appear. For example, yt-slurp asks which kinds of video to include when a channel has more than one, and whether to get new videos or start again when you've done a channel before.
5. Watch results arrive in the list on the left. Results are written to disk in rounds of 10 videos, so a long run gives you files as it goes.

While it runs:
- **Pause** holds the run between steps, and **Resume** carries on.
- **Stop** ends it cleanly. Progress is saved; slurp the same link again to carry on where it stopped.
- The **status bar** at the bottom shows progress. Select it to open the full log.

**Reading the results list.** Each result starts with a symbol and a colour:

| Symbol | Kind | Meaning |
|---|---|---|
| ■ | Transcript | A transcript ready to use |
| ♪ | WAV | An audio file waiting for your transcription app |
| ↗ | Link | The video's YouTube address |
| ⊘ | Skipped | A video that was not transcribed. The reason is in brackets after the title |

- The list is grouped by kind: links, transcripts, WAVs, then skipped videos. The chips above it (**Links**, **Transcripts**, **WAVs**, **Skipped**) show or hide each kind.
- The **Filter by name** box narrows the list as you type. Press **Esc** to clear it.
- Select a result to see it on the right. Double-click it to open it: a transcript opens in your text editor, a WAV opens its folder, and a link opens in your browser.
- On the right, a transcript is shown formatted (headings, **bold** and so on). Click in it to edit the Markdown source; click elsewhere to see it formatted again.
- **Find in this file** highlights every match. Use the ‹ and › arrows, or **Enter** and **Shift+Enter**, to move between them. Type in **Replace with**, then select **Replace** (the current match) or **Replace all**.
- **↶** and **↷** (Undo and Redo) remember your last 10 changes. **Save** (or **Ctrl+S**) writes your changes; it is grey and reads **Saved** when there is nothing to save. If you move to another file with unsaved changes, yt-slurp asks whether to save them.
- Only the tools that apply are shown: links, WAVs and skipped videos can't be edited, so they show just **Delete** (and **Play** and **Stop** for a WAV).
- **Several at once.** Shift-click to select a range, or Ctrl-click to add single results. The right side lists which of them can be edited. **Replace all** then changes every selected transcript, and **Save** writes them all.
- **Delete** works on any result, and on several at once. It deletes the file, removes a link from `links.txt`, or clears a skipped video from the list. Slurping the channel again won't bring them back.

**Doing a channel again.** Pick it from **Done before**, or paste the same link, and select Slurp. yt-slurp asks whether to **get new videos and retry any that failed**, or to **start again from scratch**. Starting again keeps any transcripts you saved from your transcription app.

**Using a list of links.** Select **Use a list of links from a file** and choose a text file with one channel or playlist link per line. Lines starting with `#` are ignored.

**Keyboard use.** Every control can be reached with **Tab**, and **Enter** or **Space** activates it. On the Slurp button, the **Down** arrow key opens the menu of video kinds.

## Videos without captions

Some videos have no captions. yt-slurp downloads their audio and turns it into WAV files (16 kHz, mono) in the channel's `needs-transcription` folder. Audio over 60 minutes is split into parts at a quiet moment.

You need a transcription app that turns WAV files into text. A free one is [whisper-transcriber](https://github.com/aidanashby/whisper-transcriber), which runs OpenAI's Whisper on your own computer.

yt-slurp matches each transcript to its video by the ID in square brackets in the filename, for example `[dQw4w9WgXcQ]`, so the transcription app must keep the WAV's filename when it saves the text. whisper-transcriber does. With another app, check the first file it saves.

Then, for real videos:

1. Select **Open WAV folder** and **Launch transcription app**.
2. Drag the WAV files into your transcription app and transcribe them.
3. Save each result as a `.txt` file into the channel's `whisper-transcripts` folder. Keep the suggested filename.
4. yt-slurp notices the saved files within a few seconds and merges each video's parts into one transcript. The result appears in the list as a ■ transcript.

To use **Launch transcription app**, first tell yt-slurp where the app is: go to **Settings**, then **Transcription app**.

## What you get

Each channel or playlist gets its own folder inside `output`. To open it, select **Open results folder**.

| Item | What it is |
|---|---|
| `transcripts` | One Markdown file per video, named `Title [video ID] date.md`. Each starts with the title as a heading, then the channel, date, length, link and caption source as a list, then a line, then the transcript |
| `gemini-notebook` | Made only when you select **Make Gemini Notebook files**: the transcripts arranged for Gemini Notebook, in upload-date order. One file per video if there are 50 or fewer, otherwise 50 files of roughly equal size |
| `links.txt` | The address of every video, one per line |
| `needs-transcription` | WAV files waiting for your transcription app |
| `whisper-transcripts` | Where you save your transcription app's text |
| `manifest.csv` | One row per video, with what happened to it and why. Opens in Excel |

**Why videos are skipped:**
- they are shorter than the minimum length (5 minutes by default, which also excludes Shorts);
- they have no captions and aren't in English (transcription apps are often set up for English only);
- they are private or deleted;
- they are a live stream that hasn't finished;
- you turned that kind of output off in Settings.

Members-only and age-restricted videos are listed as needing sign-in. At the end of a run, yt-slurp offers to retry them using your browser's YouTube sign-in.

## Using the transcripts with an AI assistant

- **Claude or ChatGPT.** Add the files from the `transcripts` folder to a project, as they are. Each file starts with the video's title, channel, date and link, so answers can cite the video.
- **Gemini Notebook.** A notebook holds a limited number of sources (50 on the free plan), so a big channel needs bundling. After a slurp, select **Make Gemini Notebook files**. yt-slurp combines the transcripts into files that fit and opens the folder; add those files to your notebook. Run it again after later slurps to include new transcripts.

## Settings

Select **Settings** in the menu bar. Settings are saved for next time.

| Section | What you can change |
|---|---|
| Which videos | Ask each time, or always use chosen kinds; minimum length; a test run of the first few videos only |
| What to make | Transcripts, WAV files and links, each on or off |
| Transcripts | Caption language; a time at the start of each paragraph |
| Videos without captions | Make WAV files for videos not in English; how long each audio part can be |
| Pace | How long to wait between requests to YouTube: Normal (2 to 5 seconds), Slow (5 to 10) or Very slow (10 to 20). Slower is gentler on YouTube for very large channels |
| Where things go | The results folder |
| Transcription app | Where the app is, and a word from its window title (if left blank, its filename is used), so **Launch transcription app** brings an open copy to the front instead of starting a second one |
| Gemini Notebook files | How many files to make, and the most words in each |

## Troubleshooting

| What you see | What to do |
|---|---|
| The setup window stops with a message | Follow the advice in the message. To ask for help, copy the window's text: right-click its title bar, choose **Edit**, then **Select All**, and press **Enter** |
| "Windows protected your PC" | Select **More info**, then **Run anyway**. It appears because yt-slurp isn't signed with a paid certificate |
| Double-clicking `yt-slurp.exe` seems to do nothing | yt-slurp may already be open behind other windows. Check the taskbar |
| A message about a JavaScript runtime, or ffmpeg missing | Restart yt-slurp and select **Yes** when it offers to download them. Downloads need an internet connection |
| "Cannot read browser cookies" | Chrome, Edge and Brave lock their cookies while open. Close the browser completely (check the system tray), or sign in to YouTube in Firefox and choose Firefox |
| "Confirm you're not a bot" | YouTube is limiting requests. Wait an hour, choose a slower pace in Settings, and slurp the same link again |
| Videos marked as failed | On the **Tools** menu, select **Open the manifest in Excel** and read the error column. Slurping the same link again retries them |
| "Something went wrong" | yt-slurp saves the details to `error.log` in `%APPDATA%\yt-slurp` and offers to open that folder. If it keeps happening, [report it on GitHub](https://github.com/aidanashby/yt-slurp/issues) and attach the file |

## Privacy and responsible use

- yt-slurp runs entirely on your computer. It sends nothing anywhere except normal requests to YouTube, to GitHub when checking for updates, and to gyan.dev and GitHub when downloading ffmpeg and Deno.
- Your browser's YouTube sign-in is used only if you choose a browser when asked, only to retry members-only or age-restricted videos, and it is never saved.
- Your settings are kept in `%APPDATA%\yt-slurp`, and results in the `output` folder.
- yt-slurp contacts GitHub when it starts, to check for a newer version. It downloads ffmpeg from gyan.dev and Deno from GitHub, checking each against its published checksum.
- yt-dlp, the library yt-slurp uses to read YouTube, is built in. YouTube changes often break older yt-dlp versions, so keep yt-slurp up to date with the Update button.
- Use yt-slurp for personal research. Respect YouTube's Terms of Service and the rights of the people who made the videos: don't republish their words as your own.

## Command line

When you run yt-slurp from its source code (see [For developers](#for-developers)), everything in the window can also be done from a terminal:

```powershell
yt-slurp https://www.youtube.com/@SomeChannel
yt-slurp "https://www.youtube.com/playlist?list=PL..."
yt-slurp --file urls.txt
yt-slurp merge "output\Some Channel"
yt-slurp gemini "output\Some Channel"
yt-slurp smoke-wav
yt-slurp gui
```

| Option | Default | Effect |
|---|---|---|
| `--file PATH` | | Links from a text file |
| `--output DIR` | `output` | Parent folder for results |
| `--types LIST` | ask | `videos`, `shorts`, `streams` or `all` |
| `--min-minutes N` | 5 | Skip shorter videos (Shorts need `0`) |
| `--lang CODE` | `en` | Caption language |
| `--timestamps` | off | `[mm:ss]` at the start of each paragraph |
| `--no-transcripts` / `--no-wavs` / `--no-links` | off | Leave out transcripts, WAV files or `links.txt` |
| `--links-only` | off | Same as `--no-transcripts --no-wavs` |
| `--pace P` | `normal` | `normal`, `slow` or `very-slow` |
| `--update` / `--fresh` | ask | What to do when the channel has been done before |
| `--include-non-english` | off | Make WAV files for non-English videos without captions |
| `--wav-rate HZ` | 16000 | WAV sample rate |
| `--chunk-minutes N` | 60 | Split longer audio into parts; 0 turns splitting off |
| `--cookies-from-browser B` | ask | `chrome`, `edge`, `firefox`, `brave` or `none` |
| `--limit N` | all | Only the first N videos |
| `--max-sources N` | 50 | `gemini` only: number of Gemini Notebook files |
| `--max-source-words N` | 400000 | `gemini` only: words per Gemini Notebook file |
| `--delete-wavs` | off | `merge` only: delete a video's WAV files once merged |

## For developers

- The pipeline is in `yt_slurp.py`, the window in `yt_slurp_gui.py` (Tkinter), and first-run setup and updates in `yt_slurp_setup.py`. `yt_slurp_app.py` is the entry point for the `.exe`.
- To run from source: `pip install -e ".[dev]"`, then `yt-slurp gui`. You need ffmpeg and Deno installed, or let the window download them.
- The `.exe` is built on GitHub's Windows machines by `.github/workflows/build-exe.yml`. Publishing a release builds it and attaches it to the release.
- Install for development with `pip install -e ".[dev]"`, then run the tests with `python -m pytest`. The window's tests need a display; on Linux, use `xvfb-run -a python -m pytest`.
- [STATUS.md](STATUS.md) records what is done and what is next. [docs/TEST-REPORT.md](docs/TEST-REPORT.md) records the latest review.

## Licence

MIT. See [LICENSE](LICENSE). yt-slurp builds on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and [FFmpeg](https://ffmpeg.org) (LGPL/GPL), which are installed separately.
