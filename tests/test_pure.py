"""Tests for yt-slurp's pure functions. Run with:  python -m pytest"""

from pathlib import Path

import pytest

import yt_slurp as ys

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


# ----- captions -----

def test_rolling_vtt_dedupe():
    cues = ys.dedupe_cues(ys.parse_vtt(read("rolling_auto.vtt")))
    text = " ".join(c.text for c in cues)
    assert text == "welcome back to the channel today we're looking at bread so first you need flour"


def test_vtt_tags_entities_and_annotations_removed():
    cues = ys.parse_vtt(read("rolling_auto.vtt"))
    joined = " ".join(c.text for c in cues)
    assert "<" not in joined and "&nbsp;" not in joined and "[Music]" not in joined


def test_dedupe_keeps_legitimate_single_word_repeats():
    cues = [ys.Cue(0, 1, "I said no"), ys.Cue(1, 2, "no way")]
    assert [c.text for c in ys.dedupe_cues(cues)] == ["I said no", "no way"]


def test_dedupe_drops_exact_duplicate_cue():
    cues = [ys.Cue(0, 1, "hello there"), ys.Cue(1, 1.01, "hello there"), ys.Cue(1.01, 2, "hello there friend")]
    assert [c.text for c in ys.dedupe_cues(cues)] == ["hello there", "friend"]


def test_manual_json3_paragraph_on_long_pause():
    text = ys.captions_to_text(read("manual.json3"), "json3", "manual", timestamps=False)
    assert text == "Hello and welcome. Today: bread & butter.\n\nAfter a long pause."


def test_json3_timestamps():
    text = ys.captions_to_text(read("manual.json3"), "json3", "manual", timestamps=True)
    assert text.startswith("[00:00] Hello")
    assert "\n\n[00:20] After a long pause." in text


def test_auto_json3_uses_word_offsets_for_end():
    cues = ys.parse_json3(read("auto.json3"))
    assert [c.text for c in cues] == ["so today we", "bake bread"]
    assert cues[0].end == pytest.approx(0.8 + ys.WORD_DURATION_EST_S)


def test_paragraph_forced_by_hard_length():
    cues = [ys.Cue(t, t + 4.9, f"w{t}") for t in range(0, 200, 5)]  # no pauses, no full stops
    paras = ys.paragraphise(cues).split("\n\n")
    assert len(paras) == 3  # breaks at 90 s and 180 s


def test_paragraph_soft_break_after_60s_at_sentence_end():
    cues = [ys.Cue(t, t + 5, "words.") for t in range(0, 100, 5)]
    paras = ys.paragraphise(cues).split("\n\n")
    assert len(paras[0].split()) == 12  # cues from 0 to 55 s; the cue at 60 s starts a new one


def test_fmt_ts_hours():
    assert ys.fmt_ts(59) == "00:59"
    assert ys.fmt_ts(3725) == "1:02:05"


def test_choose_caption_track_prefers_manual_then_orig_auto():
    subs = {"en-GB": [{"ext": "vtt", "url": "m-gb"}], "live_chat": [{"ext": "json", "url": "x"}]}
    auto = {"en": [{"ext": "json3", "url": "a-tr"}], "en-orig": [{"ext": "json3", "url": "a-orig"}]}
    assert ys.choose_caption_track(subs, auto, "en") == ("manual", "en-GB", "m-gb", "vtt")
    assert ys.choose_caption_track({}, auto, "en") == ("auto", "en-orig", "a-orig", "json3")


def test_choose_caption_track_ignores_machine_translation():
    auto = {"en": [{"ext": "json3", "url": "translated"}], "es-orig": [{"ext": "json3", "url": "es"}]}
    assert ys.choose_caption_track({}, auto, "en") is None


def test_is_english():
    assert ys.is_english(None) and ys.is_english("en-US") and not ys.is_english("es")


# ----- filenames and paths -----

def test_safe_filename_folds_and_strips():
    assert ys.safe_filename("Café – Don't Panic! (Part 2) 🎉") == "Cafe Dont Panic Part 2"


def test_safe_filename_device_names_and_empty():
    assert ys.safe_filename("con") == "_con"
    assert ys.safe_filename("COM1") == "_COM1"
    assert ys.safe_filename("!!!") == "untitled"
    assert ys.safe_filename("日本語") == "untitled"


def test_safe_filename_cap_at_word_boundary():
    title = ys.safe_filename("word " * 40)
    assert len(title) <= ys.MAX_TITLE_LEN and not title.endswith(" ")
    assert title.split()[-1] == "word"


def test_safe_filename_keeps_hyphen_underscore():
    assert ys.safe_filename("a-b_c") == "a-b_c"


def test_video_stem_and_part_suffix():
    assert ys.video_stem("20240308", "Title", "dQw4w9WgXcQ") == "Title [dQw4w9WgXcQ] 2024-03-08"
    assert ys.part_suffix(1, 3) == " part 01 of 03"
    assert ys.part_suffix(1, 1) == ""


def test_title_budget_keeps_longest_path_under_limit():
    out = Path("C:/Users/someone/Documents/" + "deep folder/" * 6 + "output/Channel Name")
    budget = ys.title_budget(out)
    title = ys.fit_title(ys.safe_filename("x " * 200), budget)
    longest = (f"{out}/{ys.DIR_NEEDS}/"
               + ys.video_stem("20240308", title, "dQw4w9WgXcQ") + ys.part_suffix(99, 99) + ".wav")
    assert len(longest) <= ys.MAX_PATH_LEN
    assert "[dQw4w9WgXcQ] 2024-03-08 part 99 of 99.wav" in longest


def test_title_budget_capped_at_max_title():
    assert ys.title_budget(Path("C:/o")) == ys.MAX_TITLE_LEN


def test_iso_date():
    assert ys.iso_date("20240308") == "2024-03-08"
    assert ys.iso_date("") == "undated"


# ----- URLs and errors -----

@pytest.mark.parametrize("url,kind,norm", [
    ("https://www.youtube.com/@SomeHandle", "channel", "https://www.youtube.com/@SomeHandle"),
    ("youtube.com/@SomeHandle/videos", "channel", "https://www.youtube.com/@SomeHandle"),
    ("https://www.youtube.com/channel/UCabc/streams", "channel", "https://www.youtube.com/channel/UCabc"),
    ("https://www.youtube.com/c/Name/featured", "channel", "https://www.youtube.com/c/Name"),
    ("https://www.youtube.com/playlist?list=PL123", "playlist", "https://www.youtube.com/playlist?list=PL123"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL123", "playlist", "https://www.youtube.com/playlist?list=PL123"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", None),
    ("https://youtu.be/dQw4w9WgXcQ", "video", None),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "video", None),
    ("https://www.youtube.com/watch?v=x&list=RDx", "unknown", None),
    ("https://vimeo.com/123", "unknown", None),
])
def test_classify_url(url, kind, norm):
    got_kind, got_norm, _ = ys.classify_url(url)
    assert got_kind == kind
    if norm:
        assert got_norm == norm


@pytest.mark.parametrize("msg,kind", [
    ("ERROR: [youtube] x: Join this channel to get access to members-only content like this video", "needs-signin"),
    ("ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.", "needs-signin"),
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video", "private"),
    ("ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies-from-browser", "bot-check"),
    ("ERROR: [youtube] x: This live event will begin in 3 hours.", "live"),
    ("ERROR: [youtube] x: Video unavailable. This video has been removed by the uploader", "unavailable"),
    ("ERROR: Unable to download webpage: HTTP Error 429: Too Many Requests", "transient"),
    ("ERROR: Unable to download webpage: HTTP Error 503: Service Unavailable", "transient"),
    ("ERROR: Unable to download webpage: HTTP Error 404: Not Found", "other"),
    ("ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271", "cookies"),
    ("Failed to decrypt with DPAPI. See https://github.com/yt-dlp/yt-dlp/issues/10927", "cookies"),
    ("WARNING: [youtube] No supported JavaScript runtime could be found.", "js-runtime"),
])
def test_classify_error(msg, kind):
    assert ys.classify_error(msg) == kind


# ----- splitting -----

def test_plan_boundaries_equal_parts():
    assert ys.plan_boundaries(3000, 3600) == []
    assert ys.plan_boundaries(3000, 0) == []
    cuts = ys.plan_boundaries(125 * 60, 60 * 60)
    assert len(cuts) == 2
    assert cuts[0] == pytest.approx(125 * 60 / 3)


def test_choose_split_point_prefers_longest_then_nearest():
    silences = [(990, 990.5), (1050, 1052), (1110, 1112)]
    assert ys.choose_split_point(silences, 1100, lo=0, hi=5000) == pytest.approx(1111)


def test_choose_split_point_ignores_outside_window_and_bounds():
    assert ys.choose_split_point([(500, 510)], 1000, lo=0, hi=5000) is None
    assert ys.choose_split_point([(950, 960)], 1000, lo=980, hi=5000) is None


def test_parse_silencedetect_offsets_and_open_end():
    stderr = ("[silencedetect @ 0x1] silence_start: 2\n"
              "[silencedetect @ 0x1] silence_end: 5 | silence_duration: 3\n"
              "[silencedetect @ 0x1] silence_start: 200\n")
    assert ys.parse_silencedetect(stderr, 1000, 1240) == [(1002, 1005), (1200, 1240)]


def test_cuts_to_ranges_no_overlap():
    ranges = ys.cuts_to_ranges(300, [100, 210])
    assert ranges == [(0, 100), (100, 210), (210, 300)]


def test_new_style_name_moves_date_after_id():
    assert ys.new_style_name("2024-03-08 My Talk [dQw4w9WgXcQ] part 01 of 02.wav") == \
        "My Talk [dQw4w9WgXcQ] 2024-03-08 part 01 of 02.wav"
    assert ys.new_style_name("undated My Talk [dQw4w9WgXcQ].txt") == "My Talk [dQw4w9WgXcQ] undated.txt"
    assert ys.new_style_name("My Talk [dQw4w9WgXcQ] 2024-03-08.txt") is None


def test_part_of():
    assert ys.part_of("T [dQw4w9WgXcQ] 2024-03-08 part 02 of 03.wav") == (2, 3)
    assert ys.part_of("T [dQw4w9WgXcQ] 2024-03-08.wav") is None


def test_skip_reason():
    assert ys.skip_reason("skipped-short", 5) == "shorter than 5 minutes"
    assert ys.skip_reason("skipped-short", 2.5) == "shorter than 2.5 minutes"
    assert ys.skip_reason("skipped-non-english") == "not in English, no captions"
    assert ys.skip_reason("no-captions") == "no captions, WAVs turned off"
    assert ys.skip_reason("pending", error="transcripts turned off") == "has captions, transcripts turned off"
    assert ys.skip_reason("transcript") == ""


def test_transcript_sort_key_uses_manifest_date(tmp_path):
    m = ys.Manifest(tmp_path / "manifest.csv")
    m.set("aaaaaaaaaa1", upload_date="20230101")
    names = ["Zebra [aaaaaaaaaa1] 2023-01-01.txt", "Apple [bbbbbbbbbb2] 2024-05-05.txt"]
    assert sorted(names, key=lambda n: ys.transcript_sort_key(n, m))[0].startswith("Zebra")


# ----- merge -----

def test_parse_transcript_filename_title_first():
    assert ys.parse_transcript_filename("T [dQw4w9WgXcQ] 2024-03-08 part 02 of 03.txt") == ("dQw4w9WgXcQ", 2, 3)
    assert ys.parse_transcript_filename("T [dQw4w9WgXcQ] 2024-03-08.txt") == ("dQw4w9WgXcQ", 1, 1)
    assert ys.parse_transcript_filename("T [dQw4w9WgXcQ] 2024-03-08 part 01 of 02 (1).txt") == ("dQw4w9WgXcQ", 1, 2)
    assert ys.parse_transcript_filename("T [dQw4w9WgXcQ] 2024-03-08.wav") is None


def test_parse_transcript_filename():
    assert ys.parse_transcript_filename("2024-03-08 T [dQw4w9WgXcQ] part 02 of 03.txt") == ("dQw4w9WgXcQ", 2, 3)
    assert ys.parse_transcript_filename("2024-03-08 T [dQw4w9WgXcQ].txt") == ("dQw4w9WgXcQ", 1, 1)
    assert ys.parse_transcript_filename("2024-03-08 T [dQw4w9WgXcQ] (1).txt") == ("dQw4w9WgXcQ", 1, 1)
    assert ys.parse_transcript_filename("notes.txt") is None


def test_collect_whisper_files_duplicates_and_unmatched():
    files = [
        ("a/x [dQw4w9WgXcQ] part 01 of 02.txt", 10),
        ("b/x [dQw4w9WgXcQ] part 01 of 02.txt", 20),
        ("a/x [dQw4w9WgXcQ] part 02 of 02.txt", 10),
        ("a/random.txt", 5),
    ]
    found, dups, unmatched = ys.collect_whisper_files(files)
    assert found["dQw4w9WgXcQ"]["parts"] == {1: "b/x [dQw4w9WgXcQ] part 01 of 02.txt",
                                             2: "a/x [dQw4w9WgXcQ] part 02 of 02.txt"}
    assert dups == ["a/x [dQw4w9WgXcQ] part 01 of 02.txt"]
    assert unmatched == ["a/random.txt"]


def test_stitch_parts_order_and_missing():
    assert ys.stitch_parts({2: "two\n", 1: " one"}, 2) == ("one\n\ntwo", [])
    assert ys.stitch_parts({1: "one", 3: "three"}, 3) == (None, [2])


# ----- combined files -----

def test_pack_groups_never_splits_and_isolates_oversize():
    assert ys.pack_groups([40, 40, 40, 150, 10], 100) == [[0, 1], [2], [3], [4]]


def test_group_for_gemini_one_per_video_when_within_limits():
    groups, over = ys.group_for_gemini([10] * 5, 50, 100)
    assert groups == [[0], [1], [2], [3], [4]] and over == 0


def test_group_for_gemini_balanced_when_too_many_videos():
    counts = [100] * 120
    groups, over = ys.group_for_gemini(counts, 50, 10_000)
    assert len(groups) == 50 and over == 0
    assert sorted(i for g in groups for i in g) == list(range(120))
    sizes = [sum(counts[i] for i in g) for g in groups]
    assert max(sizes) - min(sizes) <= 100
    for g in groups:  # consecutive
        assert g == list(range(g[0], g[-1] + 1))


def test_group_for_gemini_overflow_when_words_exceed():
    groups, over = ys.group_for_gemini([90] * 10, 3, 200)
    assert all(sum(90 for _ in g) <= 200 for g in groups)
    assert len(groups) == 5 and over == 2


def test_split_transcript_repeats_header():
    header = "Title: T\nURL: u\n"
    body = "\n\n".join(" ".join(["w"] * 600) for _ in range(5))
    pieces = ys.split_transcript(header + "\n" + body, 1500)
    assert len(pieces) > 1
    assert all(p.startswith("Title: T\nURL: u") for p in pieces)
    assert all(len(p.split()) <= 1500 for p in pieces)
    assert sum(p.count("w") for p in pieces) == 3000


def test_build_gemini_end_to_end(tmp_path):
    t = tmp_path / ys.DIR_TRANSCRIPTS
    t.mkdir()
    for i, date in enumerate(["2024-01-01", "2023-05-05", "2024-06-01"]):
        (t / f"V{i} [{'a' * 10}{i}] {date}.txt").write_text(f"Title: V{i}\n\n" + "word " * 50, encoding="utf-8")
    stats = ys.build_gemini(tmp_path, max_sources=2, max_source_words=1000)
    gemini = sorted((tmp_path / ys.DIR_GEMINI).iterdir())
    assert stats["videos"] == 3 and len(gemini) == 2
    first = gemini[0].read_text(encoding="utf-8")
    assert first.index("Title: V1") < first.index("Title: V0")  # upload-date order
    assert gemini[0].name.startswith("01 of 02 2023-05-05 to")
    assert not (tmp_path / "claude-parts").exists()