# yt-slurp

Collects transcripts for every video in a YouTube channel or playlist, ready to give to Claude or Gemini Notebook. Videos with captions become clean text. Videos without captions become WAV files for the Whisper transcriber app, and `yt-slurp merge` brings the app's saved text back in.

## Install (Windows 11, PowerShell)

For a step-by-step walkthrough from a fresh machine, including testing, see [STATUS.md](STATUS.md).

1. Python 3.10 or later, ffmpeg and Deno (yt-dlp needs Deno to read YouTube):

   ```powershell
   winget install Gyan.FFmpeg
   winget install DenoLand.Deno
   ```

   Open a new terminal afterwards so the PATH updates.

2. In the repo folder:

   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

3. When downloads start failing, update yt-dlp first: `pip install -U "yt-dlp[default]"`.

Double-click `yt-slurp.bat` for a menu, or run `yt-slurp` in the activated terminal.

## Use

```powershell
yt-slurp https://www.youtube.com/@SomeChannel
yt-slurp https://www.youtube.com/playlist?list=PL...
yt-slurp --file urls.txt            # one URL per line, # for comments
yt-slurp merge "output\Some Channel"
yt-slurp smoke-wav
```

| Option | Default | Effect |
|---|---|---|
| `--file PATH` | | URLs from a text file |
| `--output DIR` | `output` | Parent folder for results |
| `--types LIST` | ask | `videos`, `shorts`, `streams` or `all` |
| `--min-minutes N` | 5 | Skip shorter videos (Shorts need `0`) |
| `--lang CODE` | `en` | Caption language |
| `--timestamps` | off | `[mm:ss]` at the start of each paragraph |
| `--links-only` | off | Stop after links.txt |
| `--update` / `--fresh` | ask | What to do when the folder already has a manifest |
| `--include-non-english` | off | Make WAVs for non-English videos without captions |
| `--wav-rate HZ` | 16000 | WAV sample rate |
| `--chunk-minutes N` | 60 | Split longer audio into parts; 0 disables |
| `--batch-files N` | 10 | WAVs per batch folder; 0 disables |
| `--cookies-from-browser B` | ask | `chrome`, `edge`, `firefox`, `brave` or `none`, for members-only and age-restricted videos |
| `--limit N` | all | Process only the first N videos (for testing) |
| `--chunk-words N` | 100000 | Words per Claude part (run and merge) |
| `--max-sources N` | 50 | Gemini Notebook files (run and merge) |
| `--max-source-words N` | 400000 | Words per Gemini Notebook file (run and merge) |
| `--delete-wavs` | off | Merge only: delete a video's WAVs once merged |

## Output

Each channel or playlist gets `output\<name>\`:

- `links.txt`: date, duration, title and URL of every video.
- `manifest.csv`: one row per video with its status and any error. Opens in Excel.
- `transcripts\`: one text file per video, each starting with title, channel, date, duration and URL.
- `claude-parts\`: all transcripts in date order, in files of up to 100,000 words.
- `gemini-notebook\`: one file per video when there are 50 or fewer, otherwise 50 files of roughly equal size.
- `needs-transcription\batch NN\`: WAVs for videos without captions. `needs-transcription.txt` lists them.
- `whisper-transcripts\`: where you save the Whisper app's text.

## Videos without captions

Before the first real batch, run `yt-slurp smoke-wav` and follow its instructions. It checks that the Whisper app's save dialog keeps the `[ID]` brackets in the filename. If it does not, change `ID_OPEN` and `ID_CLOSE` at the top of `yt_slurp.py`.

Then, for each batch folder:

1. Drag the batch's WAVs into the Whisper app.
2. When each finishes, click **Save as .txt** and save into `whisper-transcripts\`. Keep the suggested filename. Save every file before closing the app, because it does not keep results.
3. When the batches are done, run `yt-slurp merge "output\<name>"`.

Merge stitches a video's parts in order, adds the header, and rebuilds the combined files. It lists videos with missing parts and any text files it could not match.

## Re-runs

Running the same channel again asks whether to **update** (fetch new videos and retry failures) or **start fresh** (delete the folder's contents, except `whisper-transcripts\`, after you type `yes`). Ctrl+C stops cleanly; run again with `--update` to carry on.

## Problems

- **ffmpeg not found**: `winget install Gyan.FFmpeg`, then open a new terminal.
- **JavaScript runtime message**: `winget install DenoLand.Deno`, then open a new terminal.
- **Cookies cannot be read**: Chrome, Edge and Brave lock and encrypt their cookies on Windows. Close the browser fully, or sign in to YouTube in Firefox and choose Firefox.
- **"Confirm you're not a bot"**: YouTube is limiting requests. yt-slurp pauses and offers cookies; otherwise wait an hour and run with `--update`.

## Project status

See [STATUS.md](STATUS.md) for what is done, what still needs testing and what comes next.

## Tests

```powershell
pip install -e ".[dev]"
python -m pytest
```
