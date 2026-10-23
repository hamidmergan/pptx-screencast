"""The subtitle track: one offset per slide, and the track in the MP4."""

import shutil
import subprocess
from pathlib import Path

import pytest

from pptx_screencast import subtitles as module
from pptx_screencast.subtitles import (
    build_subtitle_srt,
    build_subtitle_vtt,
    transcribe_slides,
    vtt_language_code,
)
from pptx_screencast.video import apply_faststart, get_video_duration

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _vtt(start: str, end: str, text: str) -> str:
    return f"WEBVTT\n\n{start} --> {end}\n{text}\n"


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


class _FakeRecogniser:
    """Answers per file name, because the slides are recognised in parallel."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.calls = []

    def transcribe_verbose(self, file_path: str):
        self.calls.append(file_path)
        answer = self.answers[Path(file_path).name]
        if isinstance(answer, Exception):
            raise answer
        return answer, "en"


# -- Timing --

def test_the_second_slide_starts_after_the_first():
    track = build_subtitle_vtt(
        [[_seg(0.0, 2.0, "Slide one")], [_seg(0.0, 3.0, "Slide two")]],
        [5.0, 4.0],
    )
    assert "00:00:00.000 --> 00:00:02.000" in track
    assert "00:00:05.000 --> 00:00:08.000" in track


def test_a_silent_slide_still_shifts_the_next_one():
    track = build_subtitle_vtt([[], [_seg(0.0, 1.0, "Slide two")]], [3.0, 4.0])
    assert "00:00:03.000 --> 00:00:04.000" in track
    assert track.count("-->") == 1


def test_several_sentences_of_one_slide_stay_apart():
    track = build_subtitle_vtt(
        [[_seg(0.0, 2.0, "First sentence"), _seg(2.0, 4.0, "Second sentence")]], [5.0]
    )
    assert track.count("-->") == 2
    assert "First sentence" in track
    assert "Second sentence" in track


def test_without_recognised_text_the_track_stays_empty():
    assert build_subtitle_vtt([[], []], [3.0, 3.0]) == ""
    assert build_subtitle_srt([[], []], [3.0, 3.0]) == ""


def test_the_srt_track_carries_the_same_offsets():
    track = build_subtitle_srt(
        [[_seg(0.0, 2.0, "Slide one")], [_seg(0.0, 3.0, "Slide two")]],
        [5.0, 4.0],
    )
    assert "00:00:05,000 --> 00:00:08,000" in track


def test_a_long_segment_becomes_several_cues():
    long = (
        "At academic conferences there are several people in charge. "
        "Depending on the size of the conference there are several leads, the chairs. "
        "Those are experts from the field, usually professors and lecturers."
    )
    track = build_subtitle_vtt([[_seg(0.0, 20.0, long)]], [20.0])
    assert track.count("-->") > 1


def test_no_line_of_the_track_is_too_long():
    long = "A very long sentence without a period that simply keeps going and never stops " * 3
    track = build_subtitle_vtt([[_seg(0.0, 20.0, long)]], [20.0])
    for line in track.splitlines():
        if "-->" in line or line.strip().isdigit() or line in ("WEBVTT", ""):
            continue
        assert len(line) <= 42, line


def test_a_split_segment_keeps_the_slide_offset():
    long = "First sentence with content. " * 6
    track = build_subtitle_vtt(
        [[_seg(0.0, 2.0, "Slide one")], [_seg(0.0, 10.0, long)]],
        [5.0, 10.0],
    )
    times = [line for line in track.splitlines() if "-->" in line]
    assert len(times) > 2
    assert times[1].startswith("00:00:05.000")
    assert times[-1].endswith("00:00:15.000")


# -- Recognition per slide --

def test_every_slide_is_recognised_on_its_own(tmp_path):
    files = [tmp_path / "slide_000.mp3", tmp_path / "slide_001.mp3"]
    for path in files:
        path.write_bytes(b"x")
    client = _FakeRecogniser({
        "slide_000.mp3": [_seg(0.0, 1.0, "one")],
        "slide_001.mp3": [_seg(0.0, 1.0, "two")],
    })
    result = transcribe_slides(files, client)
    assert len(result) == 2
    assert len(client.calls) == 2


def test_a_silent_slide_is_not_recognised(tmp_path):
    path = tmp_path / "slide_001.mp3"
    path.write_bytes(b"x")
    client = _FakeRecogniser({"slide_001.mp3": [_seg(0.0, 1.0, "two")]})
    result = transcribe_slides([None, path], client)
    assert result[0] == []
    assert len(client.calls) == 1


def test_an_error_on_one_slide_does_not_take_the_rest_down(tmp_path):
    files = [tmp_path / "slide_000.mp3", tmp_path / "slide_001.mp3"]
    for path in files:
        path.write_bytes(b"x")
    client = _FakeRecogniser({
        "slide_000.mp3": RuntimeError("recogniser gone"),
        "slide_001.mp3": [_seg(0.0, 1.0, "two")],
    })
    result = transcribe_slides(files, client)
    assert result[0] == []
    assert result[1][0]["text"] == "two"


def test_the_language_code_has_three_letters():
    assert vtt_language_code("DE") == "deu"
    assert vtt_language_code("EN-US") == "eng"
    assert vtt_language_code("") == ""


# -- The track inside the video --

@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "color=c=white:s=160x120:d=4",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
         "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )
    return path


def _streams(path, kind: str) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", kind,
         "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return len([line for line in result.stdout.splitlines() if line.strip()])


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_clip_length_is_measured(clip):
    assert get_video_duration(clip) == pytest.approx(4.0, abs=0.2)


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_without_subtitles_the_video_has_no_text_track(tmp_path, clip):
    done = tmp_path / "done.mp4"
    apply_faststart(clip, done)
    assert _streams(done, "s") == 0


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_subtitles_come_in_as_their_own_track(tmp_path, clip):
    track = tmp_path / "subtitles.vtt"
    track.write_text(_vtt("00:00:00.000", "00:00:02.000", "Hello"), encoding="utf-8")
    done = tmp_path / "done.mp4"
    apply_faststart(clip, done, subtitle_path=track, subtitle_lang="eng")
    assert _streams(done, "s") == 1
    assert _streams(done, "v") == 1
    assert _streams(done, "a") == 1


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_subtitle_text_is_inside_the_video(tmp_path, clip):
    track = tmp_path / "subtitles.vtt"
    track.write_text(_vtt("00:00:00.000", "00:00:02.000", "Hello world"), encoding="utf-8")
    done = tmp_path / "done.mp4"
    apply_faststart(clip, done, subtitle_path=track, subtitle_lang="eng")
    read_back = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(done), "-map", "0:s:0", "-f", "webvtt", "-"],
        capture_output=True, text=True, check=True,
    )
    assert "Hello world" in read_back.stdout


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_notice_is_written_into_the_metadata(tmp_path, clip):
    from pptx_screencast.outro import NOTICE_TEXT

    done = tmp_path / "done.mp4"
    apply_faststart(clip, done)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment",
         "-of", "default=nw=1:nk=1", str(done)],
        capture_output=True, text=True, check=True,
    )
    assert NOTICE_TEXT in result.stdout


# -- The track in the render flow --

@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_track_is_written_with_the_offset(tmp_path, clip):
    second = tmp_path / "clip2.mp4"
    shutil.copy(clip, second)
    # The audio comes out of the finished clip, otherwise the length does not match.
    client = _FakeRecogniser({
        "stt_000.m4a": [_seg(0.0, 1.0, "one")],
        "stt_001.m4a": [_seg(0.0, 1.0, "two")],
    })
    track = module.create_subtitle_track([clip, second], tmp_path, client)
    assert track is not None
    text = track.read_text(encoding="utf-8")
    assert "00:00:00.000 --> 00:00:01.000" in text
    assert "00:00:04.000 --> 00:00:05.000" in text, "the second slide starts after the first clip"


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_silent_slides_never_reach_the_recogniser(tmp_path, clip):
    """On silence a recogniser invents text, such as a stray 'you'."""
    second = tmp_path / "clip2.mp4"
    shutil.copy(clip, second)
    client = _FakeRecogniser({"stt_001.m4a": [_seg(0.0, 1.0, "two")]})
    track = module.create_subtitle_track([clip, second], tmp_path, client, has_speech=[False, True])
    assert len(client.calls) == 1
    text = track.read_text(encoding="utf-8")
    assert "two" in text
    assert "00:00:04.000 --> 00:00:05.000" in text


def test_a_broken_recogniser_leaves_no_track(tmp_path):
    class _Broken:
        def transcribe_verbose(self, file_path):
            raise RuntimeError("no recognition model configured")

    assert module.create_subtitle_track([tmp_path / "a.mp4"], tmp_path, _Broken()) is None


# -- The step says how far it got, and gives up when its time is used up --

def test_the_progress_counts_every_clip(tmp_path):
    files = []
    for i in range(3):
        path = tmp_path / f"stt_{i:03d}.m4a"
        path.write_bytes(b"audio")
        files.append(path)
    recogniser = _FakeRecogniser({p.name: [_seg(0.0, 0.5, "Hi")] for p in files})

    seen = []
    transcribe_slides(files, recogniser, lambda done, total: seen.append((done, total)))
    assert sorted(seen) == [(1, 3), (2, 3), (3, 3)]


def test_a_silent_clip_is_counted_too(tmp_path):
    path = tmp_path / "stt_000.m4a"
    path.write_bytes(b"audio")
    recogniser = _FakeRecogniser({path.name: [_seg(0.0, 0.5, "Hi")]})
    seen = []
    transcribe_slides([path, None], recogniser, lambda done, total: seen.append(done))
    assert sorted(seen) == [1, 2]


def test_a_failed_clip_is_counted_too(tmp_path):
    path = tmp_path / "stt_000.m4a"
    path.write_bytes(b"audio")
    recogniser = _FakeRecogniser({path.name: RuntimeError("gone")})
    seen = []
    result = transcribe_slides([path], recogniser, lambda done, total: seen.append(done))
    assert result == [[]]
    assert seen == [1]


def test_a_recogniser_out_of_time_is_not_asked_again(tmp_path):
    """Forty clips at up to 26 minutes each used to hold a run for hours."""
    class _OutOfTime(_FakeRecogniser):
        def out_of_time(self):
            return True

    paths = []
    for i in range(3):
        path = tmp_path / f"stt_{i:03d}.m4a"
        path.write_bytes(b"audio")
        paths.append(path)
    recogniser = _OutOfTime({})
    assert transcribe_slides(paths, recogniser) == [[], [], []]
    assert recogniser.calls == []


def test_without_a_progress_callback_nothing_breaks(tmp_path):
    path = tmp_path / "stt_000.m4a"
    path.write_bytes(b"audio")
    recogniser = _FakeRecogniser({path.name: [_seg(0.0, 0.5, "Hi")]})
    assert transcribe_slides([path], recogniser)[0][0]["text"] == "Hi"
