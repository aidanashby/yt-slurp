# yt-slurp

yt-slurp collects the transcripts of every video on a YouTube channel or playlist, so you can give them to an AI assistant such as Claude or Gemini Notebook (formerly NotebookLM) for research and analysis. Paste a link and click **Slurp**:
- Videos with captions become clean, readable text files, each headed with the title, channel, date, length and link.
- Videos without captions become audio files, ready for a Whisper transcription app.
- yt-slurp then bundles everything into files sized for Claude and for Gemini Notebook.

It runs on Windows 10 and 11, and works on your own computer. It has no account, server or subscription.

![The yt-slurp window. A channel link is in the box at the top beside a green Slurp button. On the left is a list of results, each marked with a symbol: a square for transcripts, a musical note for audio files, an arrow for links and a crossed circle for skipped videos, with chips above the list to show or hide each kind. On the right, the selected transcript is shown with the word "yeast" highlighted by a search.](docs/screenshot.png)

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
- For videos without captions only: a Whisper transcription app that saves its results as `.txt` files, one per audio file.

You don't need to install anything else first. On its first run, yt-slurp checks for Python, ffmpeg and Deno and offers to install any that are missing, using Windows' own installer, `winget`.

## Install and first run

1. Download yt-slurp. Either:
   - on this page, select the green **Code** button, then **Download ZIP**, and unzip it into a folder you'll keep, such as `Documents\yt-slurp`; or
   - if you use Git, run `git clone https://github.com/aidanashby/yt-slurp.git`.
2. Open the folder in File Explorer and double-click **`yt-slurp.bat`**.
3. A black setup window opens and checks your computer, one step at a time. When it asks a question, press **Y** for yes or **N** for no.
   - "Install Python 3.12 ... with winget?" appears only if you have no suitable Python. Press **Y**.
   - "Install ffmpeg with winget?" appears only if ffmpeg is missing. yt-slurp uses it to make audio files. Press **Y**.
   - "Install Deno with winget?" appears only if Deno is missing. yt-dlp, the library yt-slurp uses to read YouTube, needs it. Press **Y**.
   - "A newer version of yt-slurp is available. Update now?" appears on later runs when there is an update.
4. The first run then installs yt-slurp's own libraries, which takes a minute or two.
5. The yt-slurp window opens and shows a short "How to use yt-slurp" guide.

After the first run, double-clicking `yt-slurp.bat` opens the window within a few seconds. If yt-slurp is already open, it brings that window to the front instead of opening a second one.

If the setup window stops with a message, it says what went wrong and how to fix it. See also [Troubleshooting](#troubleshooting).

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
| ♪ | WAV | An audio file waiting for your Whisper app |
| ↗ | Link | The video's YouTube address |
| ⊘ | Skipped | A video that was not transcribed. The reason is in brackets after the title |

- The chips above the list (**Links**, **Skipped**, **Transcripts**, **WAVs**) show or hide each kind.
- The **Filter by name** box narrows the list as you type. Press **Esc** to clear it.
- Select a result to see it on the right. Double-click it to open it: a transcript opens in your text editor, a WAV opens its folder, and a link opens in your browser.
- On the right, **Search in this file** highlights every match. Use the ‹ and › arrows, or **Enter** and **Shift+Enter**, to move between them.

**Doing a channel again.** Pick it from **Done before**, or paste the same link, and select Slurp. yt-slurp asks whether to **get new videos and retry any that failed**, or to **start again from scratch**. Starting again keeps any Whisper text you saved.

**Using a list of links.** Select **Use a list of links from a file** and choose a text file with one channel or playlist link per line. Lines starting with `#` are ignored.

**Keyboard use.** Every control can be reached with **Tab**, and **Enter** or **Space** activates it. On the Slurp button, the **Down** arrow key opens the menu of video kinds.

## Videos without captions

Some videos have no captions. yt-slurp downloads their audio and turns it into WAV files (16 kHz, mono) in the channel's `needs-transcription` folder. Audio over 60 minutes is split into parts at a quiet moment.

Before your first real WAV files, check that your Whisper app keeps yt-slurp's filenames. yt-slurp matches each transcript to its video by the ID in square brackets, for example `[dQw4w9WgXcQ]`. On the **Tools** menu, select **Check the Whisper app keeps filenames** and follow the steps.

Then, for real videos:

1. Select **Open WAV folder** and **Launch Whisper app**.
2. Drag the WAV files into the Whisper app and transcribe them.
3. Save each result as a `.txt` file into the channel's `whisper-transcripts` folder. Keep the suggested filename.
4. yt-slurp notices the saved files within a few seconds and merges each video's parts into one transcript. The result appears in the list as a ■ transcript.

To use **Launch Whisper app**, first tell yt-slurp where the app is: go to **Settings**, then **Whisper app**.

## What you get

Each channel or playlist gets its own folder inside `output`. To open it, select **Open results folder**.

| Item | What it is |
|---|---|
| `transcripts` | One text file per video, named `Title [video ID] date.txt` |
| `claude-parts` | All transcripts in upload-date order, joined into files of up to 100,000 words each, to attach to Claude |
| `gemini-notebook` | The same transcripts arranged for Gemini Notebook: one file per video if there are 50 or fewer, otherwise 50 files of roughly equal size |
| `links.txt` | The address of every video, one per line |
| `needs-transcription` | WAV files waiting for your Whisper app |
| `whisper-transcripts` | Where you save the Whisper app's text |
| `manifest.csv` | One row per video, with what happened to it and why. Opens in Excel |

**Why videos are skipped:**
- they are shorter than the minimum length (5 minutes by default, which also excludes Shorts);
- they have no captions and aren't in English (most Whisper apps are set up for English);
- they are private or deleted;
- they are a live stream that hasn't finished;
- you turned that kind of output off in Settings.

Members-only and age-restricted videos are listed as needing sign-in. At the end of a run, yt-slurp offers to retry them using your browser's YouTube sign-in.

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
| Whisper app | Where the app is, and a word from its window title, so yt-slurp can bring it to the front |
| Advanced | File sizes for Claude and Gemini Notebook |

## Troubleshooting

| What you see | What to do |
|---|---|
| The setup window stops with a message | Follow the advice in the message. To ask for help, copy the window's text: right-click its title bar, choose **Edit**, then **Select All**, and press **Enter** |
| Double-clicking `yt-slurp.bat` seems to do nothing | yt-slurp may already be open behind other windows. Check the taskbar |
| A message about a JavaScript runtime | Double-click `yt-slurp.bat` again; it offers to install Deno |
| "Cannot read browser cookies" | Chrome, Edge and Brave lock their cookies while open. Close the browser completely (check the system tray), or sign in to YouTube in Firefox and choose Firefox |
| "Confirm you're not a bot" | YouTube is limiting requests. Wait an hour, choose a slower pace in Settings, and slurp the same link again |
| Videos marked as failed | On the **Tools** menu, select **Open the manifest in Excel** and read the error column. Slurping the same link again retries them |
| "Something went wrong" | yt-slurp saves the details to `error.log` in `%APPDATA%\yt-slurp` and offers to open that folder. If it keeps happening, [report it on GitHub](https://github.com/aidanashby/yt-slurp/issues) and attach the file |

## Privacy and responsible use

- yt-slurp runs entirely on your computer. It sends nothing anywhere except normal requests to YouTube, to PyPI (the Python package index) when installing or updating libraries, and to GitHub when checking for updates.
- Your browser's YouTube sign-in is used only if you choose a browser when asked, only to retry members-only or age-restricted videos, and it is never saved.
- Your settings are kept in `%APPDATA%\yt-slurp`, and results in the `output` folder.
- Each week yt-slurp updates yt-dlp, the library it uses to read YouTube, to the newest version, because YouTube changes often break older versions.
- Use yt-slurp for personal research. Respect YouTube's Terms of Service and the rights of the people who made the videos: don't republish their words as your own.

## Command line

Everything in the window can also be done from a terminal. In the yt-slurp folder, activate its environment with `.venv\Scripts\Activate.ps1`, then:

```powershell
yt-slurp https://www.youtube.com/@SomeChannel
yt-slurp "https://www.youtube.com/playlist?list=PL..."
yt-slurp --file urls.txt
yt-slurp merge "output\Some Channel"
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
| `--chunk-words N` | 100000 | Words per Claude file |
| `--max-sources N` | 50 | Number of Gemini Notebook files |
| `--max-source-words N` | 400000 | Words per Gemini Notebook file |
| `--delete-wavs` | off | `merge` only: delete a video's WAV files once merged |

## For developers

- The pipeline is in `yt_slurp.py` and the window in `yt_slurp_gui.py` (Tkinter). `yt-slurp.bat` is the Windows installer and launcher.
- Install for development with `pip install -e ".[dev]"`, then run the tests with `python -m pytest`. The window's tests need a display; on Linux, use `xvfb-run -a python -m pytest`.
- [STATUS.md](STATUS.md) records what is done and what is next. [docs/TEST-REPORT.md](docs/TEST-REPORT.md) records the latest review.

## Licence

MIT. See [LICENSE](LICENSE). yt-slurp builds on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense) and [FFmpeg](https://ffmpeg.org) (LGPL/GPL), which are installed separately.
