"""Building the clips and joining them, with real ffmpeg."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from pptx_screencast import video as module
from pptx_screencast.errors import VideoError

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed"
)


@pytest.fixture
def slide_image(tmp_path):
    path = tmp_path / "slide.png"
    Image.new("RGB", (321, 241), "white").save(path)
    return path


@pytest.fixture
def speech(tmp_path):
    path = tmp_path / "speech.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "anullsrc=r=24000:cl=mono:d=2", "-c:a", "libmp3lame", str(path)],
        check=True, capture_output=True,
    )
    return path


def test_the_audio_length_is_measured(speech):
    assert module.get_audio_duration(speech) == pytest.approx(2.0, abs=0.2)


def test_a_silent_slide_counts_as_three_seconds():
    assert module.get_audio_duration(None) == module.SILENT_DURATION


def test_an_unreadable_file_is_reported(tmp_path):
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not audio")
    with pytest.raises(VideoError):
        module.get_audio_duration(broken)


def test_a_clip_ends_with_its_audio(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    assert module.get_video_duration(clip) == pytest.approx(2.0, abs=0.4)


def test_the_pause_lengthens_the_clip(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip, pause=1.0)
    assert module.get_video_duration(clip) == pytest.approx(3.0, abs=0.4)


def test_a_silent_slide_still_becomes_a_clip(tmp_path, slide_image):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, None, clip, silent_duration=2.0)
    assert module.get_video_duration(clip) == pytest.approx(2.0, abs=0.3)


def test_an_empty_audio_file_counts_as_silence(tmp_path, slide_image):
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, empty, clip, silent_duration=2.0)
    assert module.get_video_duration(clip) == pytest.approx(2.0, abs=0.3)


def test_an_odd_slide_size_is_rounded_to_an_even_one(tmp_path, slide_image):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, None, clip, silent_duration=1.0)
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(clip)],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "320,240"


def test_a_faster_voice_shortens_the_clip(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip, speed=2.0)
    assert module.get_video_duration(clip) == pytest.approx(1.0, abs=0.3)


def test_the_clips_are_joined_in_order(tmp_path, slide_image, speech):
    first = tmp_path / "a.mp4"
    second = tmp_path / "b.mp4"
    module.create_slide_video(slide_image, speech, first)
    module.create_slide_video(slide_image, None, second, silent_duration=2.0)
    joined = tmp_path / "joined.mp4"
    module.concatenate_videos([first, second], joined)
    assert module.get_video_duration(joined) == pytest.approx(4.0, abs=0.6)


@pytest.mark.skipif(
    not module.has_burn_in_support(), reason="this ffmpeg has no subtitles filter"
)
def test_burned_in_subtitles_keep_the_length(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    track = tmp_path / "subtitles.srt"
    track.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    burned = tmp_path / "burned.mp4"
    out = module.burn_in_subtitles(clip, track, burned)
    assert out == burned
    assert module.get_video_duration(out) == pytest.approx(
        module.get_video_duration(clip), abs=0.4
    )


def test_a_broken_subtitle_file_leaves_the_video_alone(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    missing = tmp_path / "nope.srt"
    burned = tmp_path / "burned.mp4"
    assert module.burn_in_subtitles(clip, missing, burned) == clip


def test_an_ffmpeg_without_the_filter_keeps_the_separate_track(tmp_path, slide_image, speech, monkeypatch):
    """A build without libass can still write the track, just not draw it."""
    monkeypatch.setattr(module, "has_burn_in_support", lambda: False)
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    track = tmp_path / "subtitles.srt"
    track.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    assert module.burn_in_subtitles(clip, track, tmp_path / "burned.mp4") == clip


def test_a_clip_with_a_pause_is_built_from_a_relative_path(tmp_path, slide_image, speech, monkeypatch):
    """The concat demuxer reads entries relative to the list file, not to the cwd."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "work").mkdir()
    module.create_slide_video(
        Path("slide.png"), Path("speech.mp3"), Path("work/clip.mp4"), pause=1.0
    )
    assert module.get_video_duration(tmp_path / "work/clip.mp4") == pytest.approx(3.0, abs=0.4)


def test_relative_clips_are_joined(tmp_path, slide_image, speech, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "work").mkdir()
    module.create_slide_video(Path("slide.png"), Path("speech.mp3"), Path("work/a.mp4"))
    module.create_slide_video(Path("slide.png"), None, Path("work/b.mp4"), silent_duration=2.0)
    module.concatenate_videos(
        [Path("work/a.mp4"), Path("work/b.mp4")], Path("work/joined.mp4")
    )
    assert module.get_video_duration(tmp_path / "work/joined.mp4") == pytest.approx(4.0, abs=0.6)


def _frame_rate(path) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().rstrip(",")


def test_the_frame_rate_of_a_clip_can_be_chosen(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip, fps=25)
    assert _frame_rate(clip) == "25/1"


def test_the_frame_rate_of_a_silent_clip_can_be_chosen(tmp_path, slide_image):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, None, clip, silent_duration=1.0, fps=12)
    assert _frame_rate(clip) == "12/1"


def test_without_a_frame_rate_the_default_is_used(tmp_path, slide_image, speech):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    assert _frame_rate(clip) == f"{module._FRAME_RATE}/1"


# -- A stuck or missing program stays inside the error contract --

def test_a_stuck_probe_is_a_video_error(tmp_path, speech, monkeypatch):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=1)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    with pytest.raises(VideoError) as info:
        module.get_audio_duration(speech)
    assert "did not finish" in str(info.value)


def test_a_missing_ffprobe_is_a_video_error(tmp_path, speech, monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(module.subprocess, "run", _missing)
    with pytest.raises(VideoError):
        module.get_video_duration(tmp_path / "anything.mp4")


def test_a_stuck_join_is_a_video_error(tmp_path, monkeypatch):
    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    with pytest.raises(VideoError):
        module.concatenate_videos([tmp_path / "a.mp4"], tmp_path / "joined.mp4")


def test_a_missing_ffmpeg_for_a_clip_is_a_video_error(tmp_path, slide_image, monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(module, "run_proc", _missing)
    with pytest.raises(VideoError):
        module.create_slide_video(slide_image, None, tmp_path / "clip.mp4")


def test_a_failed_pause_is_reported_and_not_left_to_the_next_step(
    tmp_path, slide_image, speech, monkeypatch
):
    """A silent failure here used to surface as a missing input file later on."""
    real = module.run_proc

    def _fail(cmd, timeout, run_id=None):
        if "anullsrc=r=44100:cl=stereo" in cmd:
            return subprocess.CompletedProcess(cmd, 1, "", "no such filter")
        return real(cmd, timeout=timeout, run_id=run_id)

    monkeypatch.setattr(module, "run_proc", _fail)
    with pytest.raises(VideoError) as info:
        module.create_slide_video(slide_image, speech, tmp_path / "clip.mp4", pause=1.0)
    assert "pause" in str(info.value)


def test_a_stuck_faststart_keeps_the_video(tmp_path, slide_image, speech, monkeypatch):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    data = module.apply_faststart(clip, tmp_path / "final.mp4")
    assert data == clip.read_bytes()


def test_a_stuck_burn_in_keeps_the_video(tmp_path, slide_image, speech, monkeypatch):
    clip = tmp_path / "clip.mp4"
    module.create_slide_video(slide_image, speech, clip)
    track = tmp_path / "subtitles.srt"
    track.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello\n", encoding="utf-8")
    monkeypatch.setattr(module, "has_burn_in_support", lambda: True)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=1)

    monkeypatch.setattr(module.subprocess, "run", _timeout)
    assert module.burn_in_subtitles(clip, track, tmp_path / "burned.mp4") == clip
