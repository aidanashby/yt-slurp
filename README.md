# yt-slurp

**Turn YouTube channels into text files you can read, search and share with an AI assistant.**

Paste some YouTube links, click **Slurp**, and yt-slurp saves what's said in the videos as tidy text files on your computer. yt-slurp doesn't answer questions about the videos itself. It makes the files, and you add them to an AI assistant you already use, such as Claude, ChatGPT or Gemini Notebook (formerly NotebookLM), and ask your questions there. No more scrubbing through hours of video to find one good point.

![The yt-slurp window. Channel and video links are blocks in the box at the top, beside a red Slurp button. On the left is a list of results, each marked with a symbol: a square for transcripts, a musical note for audio files, an arrow for links and a crossed circle for skipped videos, with chips above the list to show or hide each kind. On the right, the selected transcript is shown formatted, with its title as a heading and its details in bold, and the editing tools above it.](docs/screenshot.png)

## What you can do with it

- **Get a whole channel ready for your AI assistant.** Add the transcripts to Claude, ChatGPT or Gemini Notebook, then ask it things like "What does this presenter say about pricing?" Each file names its video, so the assistant can tell you where an answer came from.
- **Research a topic across several channels.** Paste all the links together and get one folder of transcripts.
- **Grab a single video.** Paste its link and read it in a couple of minutes.
- **Keep up with a channel.** Slurp it again later and yt-slurp fetches only what's new.

## Why you might like it

- **It's easy.** One program, one box, one big red button. There's nothing to set up by hand.
- **It's free and private.** It runs on your own computer, with no account or subscription.
- **It takes any mix of links.** Channels, playlists and videos, in one go. Messy lists are tidied up for you.
- **The transcripts are ready to use.** Each starts with the title, channel, date, length and link. You can read, search and edit them in the window.
- **Videos without captions aren't left out.** yt-slurp saves their sound for a transcription app to turn into text.
- **It looks after itself.** YouTube changes often, so yt-slurp updates the part that reads it and tries again by itself.
- **You can stop any time.** Your progress is saved, and it warns you before starting a very long job.

## Get started

You need Windows 10 or 11 and an internet connection.

1. **Download it.** Go to the [latest release](https://github.com/aidanashby/yt-slurp/releases/latest), select **`yt-slurp.exe`**, and move the file somewhere you'll keep it, such as your Desktop.
2. **Open it.** Double-click the file. If Windows says **"Windows protected your PC"**, select **More info**, then **Run anyway**. Windows shows this for programs that don't have a paid certificate.
3. **Say Yes** if it offers to download two free helper tools. This needs no special permissions, and can take 15 minutes or more on a slow connection.
4. **Paste a link** to a YouTube channel, playlist or video, and click **Slurp**.

Your transcripts appear in the list as they're made. Select **Open results folder** to find the files, then add them to your AI assistant ([how to do that](#using-the-transcripts-with-an-ai-assistant)).

If something goes wrong, see [Troubleshooting](#troubleshooting).

## Contents

For everyone:
- [Using yt-slurp](#using-yt-slurp)
- [Using the transcripts with an AI assistant](#using-the-transcripts-with-an-ai-assistant)
- [Videos without captions](#videos-without-captions)
- [What you get](#what-you-get)
- [Settings](#settings)
- [Troubleshooting](#troubleshooting)
- [Privacy and responsible use](#privacy-and-responsible-use)

Technical details:
- [How it works](#how-it-works)
- [Command line](#command-line)
- [For developers](#for-developers)
- [Licence](#licence)

## Using yt-slurp

1. Copy the address of a YouTube **channel**, **playlist** or **video** from your browser. Any page of a channel will do.
2. Paste it into the box at the top of the window. Add more if you like.
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

**Updates.** When there is a new version of yt-slurp, a blue **Update** button appears near the top right. Select it, and yt-slurp downloads the new version and restarts; your settings and results are kept. You can also check by hand: select **?**, then **Check for updates**.

**Where results go.** By default, `Documents\yt-slurp`. To change it, select the cog, then **Change results folder**.

**Doing a channel again.** Pick it from **Done before**, or paste the same link, and select Slurp. yt-slurp asks whether to **get new videos and retry any that failed**, or to **start again from scratch**. Starting again keeps any transcripts you saved from your transcription app.

**Several links.** Paste any mixture, separated by spaces, commas or new lines. Each becomes a block: click it to edit, or × to remove it. **Clear all** empties the box.

- If your links cover more than one channel or playlist, everything goes in one folder named after them, such as `Ben AI and jawed`. Videos that turn up twice are done once.
- Slurp the same links again, in any order, and yt-slurp finds that folder, even if you have renamed it. It asks whether to update it or start again.

**Single videos.** Paste one video link on its own and yt-slurp asks whether you want just that video, the whole channel or, if the link has one, the whole playlist. A single video goes in its channel's folder, without a links list, however short it is.

**Long runs.** If there are more than 500 videos to get, yt-slurp asks first. It lists each channel or playlist with its number of videos, and you can leave any out. Change the number in **Settings** (0 turns it off).

**Using a list of links.** Select **Use a list of links from a file** and choose a text file with one channel, playlist or video link per line. Lines starting with `#` are ignored. Each channel or playlist gets its own folder, and a video link that is part of a playlist means the playlist.

**Keyboard use.** Every control can be reached with **Tab**, and **Enter** or **Space** activates it. On the Slurp button, the **Down** arrow key opens the menu of video kinds.

## Using the transcripts with an AI assistant

- **Claude or ChatGPT.** Add the files from the `transcripts` folder to a project, as they are. Each file starts with the video's title, channel, date and link, so answers can cite the video.
- **Gemini Notebook.** A notebook holds a limited number of sources (50 on the free plan), so a big channel needs bundling. After a slurp, select **Make Gemini Notebook files**. yt-slurp combines the transcripts into files that fit and opens the folder; add those files to your notebook. Run it again after later slurps to include new transcripts.

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

Each channel or playlist gets its own folder inside your results folder. Links for several, pasted together, share one. To open it, select **Open results folder**.

| Item | What it is |
|---|---|
| `transcripts` | One Markdown file per video, named `Title [video ID] date.md`. Each starts with the title as a heading, then the channel, date, length, link and caption source as a list, then a line, then the transcript |
| `gemini-notebook` | Made only when you select **Make Gemini Notebook files**: the transcripts arranged for Gemini Notebook, in upload-date order. One file per video if there are 50 or fewer, otherwise 50 files of roughly equal size |
| `links.txt` | The address of every video, one per line (not made when you slurp only single videos) |
| `needs-transcription` | WAV files waiting for your transcription app |
| `whisper-transcripts` | Where you save your transcription app's text |
| `manifest.csv` | One row per video, with what happened to it and why. Opens in Excel |

**Why videos are skipped:**
- they are shorter than the minimum length (5 minutes by default, which also excludes Shorts), unless you pasted the video's own link;
- they have no captions and aren't in English (transcription apps are often set up for English only);
- they are private or deleted;
- they are a live stream that hasn't finished;
- you turned that kind of output off in Settings.

Members-only and age-restricted videos are listed as needing sign-in. At the end of a run, yt-slurp offers to retry them using your browser's YouTube sign-in.

## Settings

Select the cog at the top right. The wrench beside it is the Tools menu, and **?** is Help. Settings are saved for next time.

| Section | What you can change |
|---|---|
| Which videos | Ask each time, or always use chosen kinds; minimum length; a test run of the first few videos only; how many videos to warn about |
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
| A slurp stops with a message | Select **Try again** if it is offered. To ask for help, select **Copy details** and paste them |
| "Windows protected your PC" | Select **More info**, then **Run anyway**. It appears because yt-slurp isn't signed with a paid certificate |
| Double-clicking `yt-slurp.exe` seems to do nothing | yt-slurp may already be open behind other windows. Check the taskbar |
| Setup stops with "certificate verify failed: certificate has expired" | Versions before 0.2.3 fail this way on some PCs. Download the latest `yt-slurp.exe` from the [releases page](https://github.com/aidanashby/yt-slurp/releases/latest) and run it instead |
| A message that ffmpeg or Deno could not be set up, or that yt-dlp cannot read YouTube | Check your internet connection and select **Try again**. If yt-dlp has no fix yet, try again in a few days: yt-slurp installs it by itself |
| "Cannot read browser cookies" | Chrome, Edge and Brave lock their cookies while open. Close the browser completely (check the system tray), or sign in to YouTube in Firefox and choose Firefox |
| "Confirm you're not a bot" | YouTube is limiting requests. Wait an hour, choose a slower pace in Settings, and slurp the same link again |
| Videos marked as failed | On the Tools menu (the wrench), select **Open the manifest in Excel** and read the error column. Slurping the same link again retries them |
| "Something went wrong" | yt-slurp saves the details to `error.log` in `%APPDATA%\yt-slurp` and offers to open that folder. If it keeps happening, [report it on GitHub](https://github.com/aidanashby/yt-slurp/issues) and attach the file |

## Privacy and responsible use

- yt-slurp runs on your own computer. It sends nothing anywhere except ordinary requests to YouTube, and to the sites it downloads its updates and tools from (listed in [How it works](#how-it-works)).
- Your browser's YouTube sign-in is used only if you choose a browser when asked, only to retry members-only or age-restricted videos, and it is never saved.
- Your settings are kept in `%APPDATA%\yt-slurp`, and your results in the folder you choose.
- Use yt-slurp for personal research. Respect YouTube's Terms of Service and the rights of the people who made the videos: don't republish their words as your own.

## How it works

yt-slurp is a Python and Tkinter app, packed into one `.exe` with PyInstaller. It reads YouTube with [yt-dlp](https://github.com/yt-dlp/yt-dlp), which uses Deno to solve YouTube's JavaScript challenges, and makes WAV files with ffmpeg.

| Part | Where it comes from | Where it is kept |
|---|---|---|
| ffmpeg | gyan.dev, on first run or if missing or broken | `%LOCALAPPDATA%\yt-slurp\tools` |
| Deno | GitHub, on first run or if missing, broken or too old | `%LOCALAPPDATA%\yt-slurp\tools` |
| yt-dlp and its solver | built in; newer versions from PyPI | `%LOCALAPPDATA%\yt-slurp\engine` |
| yt-slurp itself | GitHub releases, when you select **Update** | the `.exe` you run |

- Working copies of ffmpeg and Deno already on the computer are used if there are any. Both are checked by running them, and downloads are checked against their published checksums where there are any.
- **yt-dlp updates** are code that yt-slurp downloads and runs. It checks PyPI once a day when a slurp starts, skipping releases less than 48 hours old, and checks again at once (taking the newest) if YouTube cannot be read. Each download's checksum is verified, it is tested in a separate process, and the previous copy stays if the test fails.
- Downloads check certificates against certifi's list, as yt-dlp does, and need no admin rights.

## Command line

When you run yt-slurp from its source code (see [For developers](#for-developers)), everything in the window can also be done from a terminal:

```powershell
yt-slurp https://www.youtube.com/@SomeChannel
yt-slurp "https://www.youtube.com/playlist?list=PL..."
yt-slurp https://www.youtube.com/@SomeChannel https://youtu.be/VIDEO_ID
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
| `--separate` | off | With several URLs: a folder for each channel or playlist (always so with `--file`) |
| `--whole-channel` | off | With a video URL: do the video's whole channel |
| `--warn-over N` | 0 | Ask before doing more than N videos (0 never asks) |

## For developers

- The pipeline is in `yt_slurp.py`, the window in `yt_slurp_gui.py` (Tkinter), and first-run setup and updates in `yt_slurp_setup.py`. `yt_slurp_engine.py` keeps yt-dlp current, and `hooks/` makes PyInstaller bundle the whole standard library, so newer versions load in the `.exe`. `yt_slurp_app.py` is the entry point for the `.exe`.
- To run from source: `pip install -e ".[dev]"`, then `yt-slurp gui`. On Windows, yt-slurp downloads ffmpeg and Deno if they are missing; elsewhere, install them yourself.
- The `.exe` is built on GitHub's Windows machines by `.github/workflows/build-exe.yml`. Publishing a release builds it and attaches it to the release.
- Install for development with `pip install -e ".[dev]"`, then run the tests with `python -m pytest`. The window's tests need a display; on Linux, use `xvfb-run -a python -m pytest`.
- [STATUS.md](STATUS.md) records what is done and what is next. [docs/TEST-REPORT.md](docs/TEST-REPORT.md) records the October 2026 review of version 0.1.

## Licence

MIT. See [LICENSE](LICENSE). yt-slurp builds on [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), which is built in, and [FFmpeg](https://ffmpeg.org) (LGPL/GPL) and [Deno](https://deno.com) (MIT), which are downloaded separately.
