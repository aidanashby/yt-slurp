# yt-slurp: pre-release review and test report

13th October 2026. Review done before making the repository public.

## Summary

No security problems were found that block release. The review found and fixed:
- a performance bug in search highlighting;
- three accessibility problems: keyboard access, colour contrast, and information shown by colour alone;
- two places where hostile or damaged input could cause trouble.

All 108 automated tests pass. Two things remain untested: live YouTube requests and the Windows launcher, `yt-slurp.bat`, because the build environment can reach neither YouTube nor Windows.

## What was tested

| Kind | What was done | Result |
|---|---|---|
| Smoke | Clean clone, fresh virtual environment, `pip install -e ".[dev]"`; `yt-slurp --help`, `smoke-wav`, then `merge` on the smoke folder; the window opened and driven through a full run | Pass |
| Regression | Full suite: 108 tests (pure functions, offline end-to-end runs with a fake YouTube layer and real ffmpeg, the window under a virtual display) | 108 passed |
| Negative and edge cases | 30 new tests: empty, non-YouTube, mix, search-page and single-video links; empty, comment-only and missing link files; unknown options; malformed video IDs, including path-traversal strings; damaged `manifest.csv` and `settings.json`; very long, non-Latin and reserved-name titles; an output path too long for Windows; missing ffmpeg; a folder locked by another run, and a stale lock from a dead one; Stop while paused; stray and non-text files in the Whisper folder | Pass, after the fixes below |
| Acceptance | Every requirement from the specification and later requests checked against a test or a screenshot (see the list below) | Pass, except the items under "What was not tested" |
| Integration | yt-dlp is used as a library. Its parameters (`js_runtimes`, `cookiesfrombrowser`, `extract_flat`), its error messages (members-only, age-restricted, private, bot check, rate limits, cookie failures, missing JavaScript runtime) and its caption track naming (`-orig`) were checked against the installed yt-dlp 2026.08.19 source | Consistent |
| Performance | 2,000 transcripts of 3,000 words each (6 million words) through the Claude and Gemini builder; a 2,000-video folder loaded into the window; 3,000 results added live; filter and chips over 3,000 results; preview and search of a 200,000-word transcript | All under 1.1 s except adding 3,000 results live (3.3 s in total). Search was 577 s before the fix, 0.04 s after |
| Accessibility | Keyboard-only walk-through of the window; contrast ratio computed for every text and button colour pair; check that no information is shown by colour alone | Pass, after the fixes below |
| Security | Manual review of everything that takes outside input (YouTube titles, IDs, captions, the Whisper app's files, settings, the launcher); `bandit` static analysis; `pip-audit` against the installed dependencies; a search of the code and git history for secrets | No blocking issues (details below) |

## Fixed during the review

1. **Search highlighting was very slow in long transcripts.** Each highlight counted characters from the start of the text, so the time grew with the square of the number of matches: 44,000 matches took nearly 10 minutes. Now positions are converted once, highlights are added in batches, at most 2,000 are highlighted (the arrows still visit every match), and the search waits until typing pauses.
2. **Drawn buttons and chips could not be used from the keyboard.** Slurp, Pause, Stop, the bottom buttons, the chips and the "Use a list of links from a file" link now take keyboard focus, show a focus ring, and work with Enter or Space. The Slurp menu opens with the Down arrow key. The Tab order now runs top to bottom.
3. **Colour contrast below WCAG AA (4.5:1).** The green, blue and red buttons, the amber "skipped" text and the grey hint text were darkened. Every pair now measures 5.1:1 or better.
4. **Colour was the only difference between a video's link and its transcript.** Each kind now has its own symbol as well: ■ transcript, ♪ WAV, ↗ link, ⊘ skipped.
5. **Video IDs are now validated before they reach a file path.** Only the 11-character YouTube form is accepted, so a strange listing entry such as `../../x` is ignored.
6. **A damaged or hand-edited `settings.json` could stop the window opening.** Each setting is now checked, and anything wrong falls back to its default.

## Security review

- **Secrets.** None in the code or git history. The app stores no passwords or tokens. Browser cookies are read only when you choose a browser for a sign-in retry, and they are never written to disk.
- **Command injection.** ffmpeg, ffprobe, PowerShell, git and pytest are all run with argument lists, never through a shell. YouTube titles are reduced to letters, digits, spaces, hyphens and underscores before they are used in a filename.
- **Path traversal.** Filenames come from cleaned titles and validated IDs (fix 5). Output paths are capped at 240 characters.
- **Files from other programs.** The merge step reads only `.txt` files from the channel's own folders and treats them as plain text.
- **bandit.** It reported 17 low-severity notes and nothing at medium or high severity. All were reviewed:
  - starting ffmpeg, PowerShell and similar programs by name, found on the PATH: expected, because the user installs them;
  - `random` used for delays between requests, not for security;
  - one deliberate `try`/`except`/`pass` when closing yt-dlp.
- **pip-audit.** No known vulnerabilities in the installed dependencies: yt-dlp 2026.08.19, yt-dlp-ejs 0.8.0 and their requirements.
- **Supply chain (accepted risk).**
  - Each week the launcher updates yt-dlp to the newest release without a pinned version.
  - With the user's agreement, it runs `git pull` from this repository's `main` branch.
  - Both are normal for a tool that has to keep pace with YouTube, but they mean a compromised yt-dlp release or GitHub account would reach users. The README says so.
- **Personal details in the repository.**
  - The owner's Windows path appears in older commits of `STATUS.md`; the current version is generic.
  - The first commit carries the owner's email address, as any GitHub commit does.
  - Commit messages link to the Claude Code session that built the tool; only the owner can open those links.
  - Removing any of these would mean rewriting history with a force-push, which was not done.

## What was not tested, and why

| Not tested | Why | How to cover it |
|---|---|---|
| Live YouTube requests (listing, details, captions, audio download, cookies, bot checks) | The build environment's network blocks YouTube | The first-run checklist in `STATUS.md`, on Windows |
| `yt-slurp.bat` | It is a Windows batch file; the build environment is Linux, without Windows or Wine | The same checklist. The file was reviewed line by line for `cmd` quirks: brackets in blocks, quoting in `for /f`, and a script that updates itself |
| The Whisper app's save dialog keeping `[ID]` brackets | It needs your Whisper app on Windows | Tools, then **Check the Whisper app keeps filenames** |
| The window on Windows itself (fonts, display scaling above 100%, the native drop shadow, taskbar icon) | Rendered here on Linux only | Look over the first run on Windows |
| Screen readers | Tkinter gives screen readers very little information, and none was available here | A known limit of the toolkit. The README and the keyboard support make the main tasks possible without a mouse |
| Cross-browser and cross-device | Not applicable: yt-slurp is a Windows desktop app, not a web page or mobile app | None needed |
| macOS and Linux as targets | Not supported: the launcher and some window features are Windows-only. The pipeline and tests do run on Linux | None planned |

## Known issues

- **Screen reader support is limited** by Tkinter. Keyboard access works, but list items and drawn buttons are not announced well.
- **Very long single-line text** (over a million characters without line breaks) is slow to search, because the Tk text widget struggles with long lines. Real transcripts have paragraph breaks, so this should not arise in use.
- **Unpinned yt-dlp updates** (accepted risk, above).
- **Auto-captions** are only as good as YouTube's speech recognition. Names and technical terms are often wrong.

## Acceptance checklist

Every item is covered by a test or a screenshot, apart from those needing live YouTube or Windows.

| Requirement | Checked by |
|---|---|
| Channel and playlist links, `--file` lists, single videos refused | `test_classify_url`, `test_bad_urls_are_refused`, `test_url_file_*`, `test_single_video_rejected` |
| Type choice for channels, and the Slurp menu for one type | `test_build_argv_maps_settings`, pipeline tests |
| Minimum length filter, skipped videos listed with a reason | `test_full_pipeline`, `test_skip_reason`, GUI tests |
| Captions to clean text: rolling duplicates removed, paragraphs, timestamps, header | `test_rolling_vtt_dedupe`, `test_manual_json3_*`, `test_paragraph_*` |
| Only the original-language auto track; no machine translations | `test_choose_caption_track_*` |
| WAVs: 16 kHz, mono, 16-bit, split at silence, no overlap | `test_full_pipeline` (checked with ffprobe), splitting tests |
| Title-first filenames, safe on Windows, under 240 characters | `test_safe_filename_*`, `test_title_budget_*`, edge tests |
| `links.txt` with URLs only | `test_full_pipeline`, GUI test |
| Merge by `[id]` and `part NN of NN`; missing parts and stray files listed | merge tests, `test_merge_ignores_stray_and_empty_files` |
| Claude and Gemini files within limits, in date order | `test_group_*`, `test_build_combined_end_to_end`, performance run |
| Update, fresh (keeping Whisper text), cookie retry, rounds of 10, pace, pause, stop | pipeline and edge tests |
| Window: unified colour-coded list, chips, filter, search, settings window, status bar and log, auto-merge, keyboard use | GUI tests, keyboard walk-through, screenshot |

## Making the repository public

GitHub's tools here cannot change a repository's visibility, so the owner does this:

1. On GitHub, open the repository and select **Settings**.
2. Scroll to **Danger Zone** at the bottom of the **General** page.
3. Select **Change visibility**, then **Change to public**, and confirm.
