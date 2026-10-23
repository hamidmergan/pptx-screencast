"""Splitting long recogniser segments into short cues."""

from pptx_screencast.subtitle_converter import (
    segments_to_srt,
    split_long_segments,
    vtt_to_segments,
    vtt_to_srt,
)

# A real segment, 553 characters over 29.3 seconds.
_LONG = (
    "Who is responsible. At academic conferences there are several people in "
    "charge. Depending on the size of the conference there are several leads, "
    "the so called chairs. These are experts from the field, usually "
    "professors and lecturers, but practitioners from companies can hold the "
    "role as well. Then there is always an organising committee. Those are "
    "mostly staff of the hosting institution. They are responsible for the "
    "organisation and the schedule, which means rooms, equipment, the social "
    "programme, catering and so on and so forth."
)


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


def test_a_short_segment_is_passed_through():
    segments = split_long_segments([_seg(1.0, 3.0, "Good morning everyone.")])
    assert segments == [_seg(1.0, 3.0, "Good morning everyone.")]


def test_a_long_segment_is_split():
    assert len(split_long_segments([_seg(0.0, 29.3, _LONG)])) > 1


def test_no_line_is_longer_than_the_limit():
    for seg in split_long_segments([_seg(0.0, 29.3, _LONG)]):
        for line in seg["text"].split("\n"):
            assert len(line) <= 42, line


def test_at_most_two_lines_per_cue():
    for seg in split_long_segments([_seg(0.0, 29.3, _LONG)]):
        assert len(seg["text"].split("\n")) <= 2


def test_no_word_is_cut_in_half():
    """All words come back out in the same order."""
    segments = split_long_segments([_seg(0.0, 29.3, _LONG)])
    out = " ".join(s["text"].replace("\n", " ") for s in segments).split()
    assert out == _LONG.split()


def test_the_times_stay_inside_and_leave_no_gap():
    segments = split_long_segments([_seg(10.0, 39.3, _LONG)])
    assert segments[0]["start"] == 10.0
    assert segments[-1]["end"] == 39.3
    for before, after in zip(segments, segments[1:]):
        assert before["end"] == after["start"]
        assert before["start"] < before["end"]


def test_the_split_prefers_the_end_of_a_sentence():
    text = (
        "The conference starts on Monday at nine in the big lecture hall. "
        "After that it continues with the talks of the working groups."
    )
    segments = split_long_segments([_seg(0.0, 8.0, text)])
    assert segments[0]["text"].replace("\n", " ").endswith("hall.")


def test_an_overlong_word_stays_whole():
    """No endless loop when a single word blows the limit."""
    word = "Danube" + "steamshipcompanycaptainsoffice" * 4
    segments = split_long_segments([_seg(0.0, 4.0, word)])
    assert " ".join(s["text"].replace("\n", " ") for s in segments).split() == [word]


def test_an_empty_list_stays_empty():
    assert split_long_segments([]) == []


def test_srt_counts_from_one_and_uses_a_comma():
    text = segments_to_srt([_seg(0.0, 1.5, "Hello."), _seg(1.5, 3.0, "Again.")])
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,500")
    assert "2\n00:00:01,500 --> 00:00:03,000" in text


def test_vtt_can_be_read_back_and_written_as_srt():
    vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.500\nHello.\n"
    assert vtt_to_segments(vtt) == [{"start": 0.0, "end": 1.5, "text": "Hello."}]
    assert "00:00:00,000 --> 00:00:01,500" in vtt_to_srt(vtt)
