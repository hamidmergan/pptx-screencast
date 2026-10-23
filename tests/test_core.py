"""The whole way from a deck to the finished MP4.

LibreOffice is not needed here: the slide rendering is replaced by plain
pictures, everything after it is the real code with real ffmpeg.
"""

import shutil
import subprocess
from fractions import Fraction

import pytest
from PIL import Image

from pptx_screencast import core
from pptx_screencast.errors import ScriptError, SlideError
from pptx_screencast.script_file import parse_script_file, write_script_file
from pptx_screencast.video import get_video_duration

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _rate(path, entry: str) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", f"stream={entry}", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().rstrip(",")


@pytest.fixture
def deck(tmp_path):
    """A deck of four slides with notes, copied so the output lands in tmp."""
    from _pptx_fixtures import notes_pptx

    path = tmp_path / "deck.pptx"
    path.write_bytes(notes_pptx(["Note one.", "", "Note three.", "Note four."]))
    return path


@pytest.fixture
def no_libreoffice(monkeypatch):
    """Slide pictures without LibreOffice, one PNG per slide."""
    def _images(pptx, folder, dpi=100, max_workers=4):
        count = len(core.extract_text_per_slide(pptx))
        made = []
        for i in range(count):
            path = folder / f"slide-{i + 1}.png"
            Image.new("RGB", (160, 120), "white").save(path)
            made.append(path)
        return made

    monkeypatch.setattr(core, "pptx_to_images", _images)
    monkeypatch.setattr(core, "require_tools", lambda **kwargs: None)


def _options(server, **extra):
    options = dict(
        base_url=server.base_url,
        model="chat",
        tts_model="tts",
        voice="alloy",
    )
    options.update(extra)
    return options


# -- write_script --

def test_the_script_file_has_one_heading_per_slide(deck, server, tmp_path):
    written = core.write_script(deck, tmp_path / "deck.md", base_url=server.base_url, model="chat")
    scripts = parse_script_file(written.read_text(encoding="utf-8"))
    assert len(scripts) == 4
    assert all(s.strip() for s in scripts)


def test_the_script_file_lands_next_to_the_deck(deck, server):
    written = core.write_script(deck, base_url=server.base_url, model="chat")
    assert written.parent == deck.parent
    assert written.suffix == ".md"


def test_notes_become_the_script_without_asking_the_model(deck, server):
    written = core.write_script(deck, notes=True, base_url=server.base_url, model="chat")
    scripts = parse_script_file(written.read_text(encoding="utf-8"))
    assert scripts == ["Note one.", "", "Note three.", "Note four."]
    assert server.count("chat") == 0


def test_a_script_can_be_translated_on_the_way_out(deck, server):
    written = core.write_script(
        deck, notes=True, translate="German", base_url=server.base_url, model="chat"
    )
    scripts = parse_script_file(written.read_text(encoding="utf-8"))
    assert scripts[0].startswith("[translated]")
    assert scripts[1] == "", "an empty slide costs no request"


def test_writing_a_script_needs_no_voice(deck, server):
    core.write_script(deck, base_url=server.base_url, model="chat")
    assert server.count("speech") == 0


# -- make_video --

@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_a_deck_becomes_one_mp4(deck, server, tmp_path, no_libreoffice):
    out = core.make_video(deck, tmp_path / "deck.mp4", **_options(server))
    assert out.exists()
    assert get_video_duration(out) > 0


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_narration_comes_from_a_script_file(deck, server, tmp_path, no_libreoffice):
    script = write_script_file(["One.", "Two.", "Three.", "Four."], tmp_path / "deck.md")
    core.make_video(deck, tmp_path / "deck.mp4", script=script, **_options(server))
    assert server.count("chat") == 0
    assert server.count("speech") == 4


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_only_the_chosen_slides_are_spoken(deck, server, tmp_path, no_libreoffice):
    core.make_video(deck, tmp_path / "deck.mp4", slides=[0, 2], **_options(server))
    assert server.count("speech") == 2


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_a_silent_slide_costs_no_speech_request(deck, server, tmp_path, no_libreoffice):
    core.make_video(deck, tmp_path / "deck.mp4", notes=True, **_options(server))
    assert server.count("speech") == 3, "slide two has no note"


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_subtitles_are_written_next_to_the_video(deck, server, tmp_path, no_libreoffice):
    out = core.make_video(
        deck, tmp_path / "deck.mp4",
        **_options(server, subtitles=True, stt_model="whisper"),
    )
    assert out.with_suffix(".vtt").exists()
    assert out.with_suffix(".srt").exists()
    assert "WEBVTT" in out.with_suffix(".vtt").read_text(encoding="utf-8")


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_without_a_recognition_model_there_are_no_subtitles(deck, server, tmp_path, no_libreoffice):
    out = core.make_video(deck, tmp_path / "deck.mp4", **_options(server, subtitles=True))
    assert not out.with_suffix(".vtt").exists()
    assert server.count("transcribe") == 0


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_progress_names_every_step(deck, server, tmp_path, no_libreoffice):
    steps = []
    core.make_video(
        deck, tmp_path / "deck.mp4",
        progress=lambda step, done, total: steps.append(step),
        **_options(server),
    )
    assert {"scripts", "speak", "video", "join"} <= set(steps)


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_work_directory_is_kept_when_asked(deck, server, tmp_path, no_libreoffice):
    work = tmp_path / "work"
    core.make_video(deck, tmp_path / "deck.mp4", work_dir=str(work), **_options(server))
    assert work.exists()
    assert any(work.rglob("slide_000.mp3"))


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_a_relative_work_directory_works(deck, server, tmp_path, no_libreoffice, monkeypatch):
    """The default pause puts every clip through the audio concat list."""
    monkeypatch.chdir(tmp_path)
    out = core.make_video(deck, tmp_path / "deck.mp4", work_dir="work", **_options(server))
    assert get_video_duration(out) > 0
    assert (tmp_path / "work" / "audio" / "slide_000.mp3").exists()


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_a_reused_work_directory_keeps_no_file_of_the_run_before(
    deck, server, tmp_path, no_libreoffice
):
    """A 12 slide run must not leave anything a 4 slide run could pick up."""
    work = tmp_path / "work"
    (work / "images").mkdir(parents=True)
    (work / "audio").mkdir(parents=True)
    for i in range(1, 13):
        (work / "images" / f"slide-{i:02d}.png").write_bytes(b"stale")
    (work / "audio" / "slide_007.mp3").write_bytes(b"stale")

    core.make_video(deck, tmp_path / "deck.mp4", work_dir=str(work), **_options(server))

    assert sorted(p.name for p in (work / "images").glob("*.png")) == [
        f"slide-{i}.png" for i in range(1, 5)
    ]
    assert not (work / "audio" / "slide_007.mp3").exists()


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_fps_setting_reaches_the_clips_and_the_finished_video(
    deck, server, tmp_path, no_libreoffice
):
    work = tmp_path / "work"
    out = core.make_video(
        deck, tmp_path / "deck.mp4", fps=20, work_dir=str(work), **_options(server)
    )
    assert _rate(work / "clip_000.mp4", "r_frame_rate") == "20/1"
    assert _rate(work / "clip_notice.mp4", "r_frame_rate") == "20/1"
    assert float(Fraction(_rate(out, "avg_frame_rate"))) == pytest.approx(20, abs=0.5)


# -- What is refused --

def test_a_script_file_with_the_wrong_count_is_refused(deck, server, tmp_path, no_libreoffice):
    script = write_script_file(["One.", "Two."], tmp_path / "deck.md")
    with pytest.raises(ScriptError):
        core.make_video(deck, tmp_path / "deck.mp4", script=script, **_options(server))


def test_an_empty_slide_choice_is_refused(deck, server, tmp_path, no_libreoffice):
    with pytest.raises(SlideError):
        core.make_video(deck, tmp_path / "deck.mp4", slides=[99], **_options(server))


def test_a_deck_over_the_limit_is_refused(deck, server, tmp_path, no_libreoffice):
    with pytest.raises(SlideError) as info:
        core.make_video(deck, tmp_path / "deck.mp4", max_slides=2, **_options(server))
    assert "--slides" in str(info.value)


def test_a_file_that_is_not_a_deck_is_reported(tmp_path, server):
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"this is not a zip file")
    with pytest.raises(SlideError) as info:
        core.write_script(broken, base_url=server.base_url, model="chat")
    assert "could not be read" in str(info.value)


def test_a_file_that_is_not_a_deck_is_reported_for_the_notes_too(tmp_path, server):
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"PK\x03\x04 but truncated")
    with pytest.raises(SlideError):
        core.write_script(broken, notes=True, base_url=server.base_url, model="chat")


# -- What the finished files really say --

def _streams(path) -> list:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return [line.strip().rstrip(",") for line in result.stdout.splitlines() if line.strip()]


def _comment(path) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=comment",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().rstrip(",")


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_cue_times_of_the_finished_track_match_the_clips(
    deck, server, tmp_path, no_libreoffice
):
    """The notice clip runs first, so every cue sits behind it.

    The fake recogniser answers three words of half a second each, so the
    first cue of a slide is at the offset of that slide and nowhere else.
    """
    from pptx_screencast.subtitle_converter import vtt_to_cues
    from pptx_screencast.video import SILENT_DURATION

    work = tmp_path / "work"
    out = core.make_video(
        deck, tmp_path / "deck.mp4", work_dir=str(work),
        **_options(server, subtitles=True, stt_model="whisper"),
    )

    cues = vtt_to_cues(out.with_suffix(".vtt").read_text(encoding="utf-8"))
    assert [c["text"] for c in cues[:3]] == ["Hello", "there", "again"]
    assert cues[0]["start"] == pytest.approx(SILENT_DURATION, abs=0.001)
    assert cues[0]["end"] == pytest.approx(SILENT_DURATION + 0.5, abs=0.001)

    # Slide two starts behind the notice clip and the clip of slide one.
    first_clip = get_video_duration(work / "clip_000.mp4")
    assert cues[3]["start"] == pytest.approx(SILENT_DURATION + first_clip, abs=0.001)

    # Slide two has no note but a generated script, so it speaks as well.
    assert len(cues) == 3 * 4, "three words per slide, four slides"


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_notice_frames_the_video_and_stands_in_the_metadata(
    deck, server, tmp_path, no_libreoffice
):
    from pptx_screencast.outro import NOTICE_TEXT
    from pptx_screencast.video import SILENT_DURATION

    work = tmp_path / "work"
    out = core.make_video(
        deck, tmp_path / "deck.mp4", work_dir=str(work), **_options(server)
    )
    notice = get_video_duration(work / "clip_notice.mp4")
    assert notice == pytest.approx(SILENT_DURATION, abs=0.3)
    clips = [get_video_duration(work / f"clip_{i:03d}.mp4") for i in range(4)]
    # Notice, four slides, notice again.
    assert get_video_duration(out) == pytest.approx(sum(clips) + 2 * notice, abs=0.3)
    assert _comment(out) == NOTICE_TEXT


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_finished_file_carries_the_subtitle_track(deck, server, tmp_path, no_libreoffice):
    out = core.make_video(
        deck, tmp_path / "deck.mp4",
        **_options(server, subtitles=True, stt_model="whisper"),
    )
    assert _streams(out) == ["video", "audio", "subtitle"]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_srt_holds_the_same_cues_as_the_vtt(deck, server, tmp_path, no_libreoffice):
    from pptx_screencast.subtitle_converter import vtt_to_cues

    out = core.make_video(
        deck, tmp_path / "deck.mp4",
        **_options(server, subtitles=True, stt_model="whisper"),
    )
    vtt = vtt_to_cues(out.with_suffix(".vtt").read_text(encoding="utf-8"))
    srt_text = out.with_suffix(".srt").read_text(encoding="utf-8")
    srt = vtt_to_cues(srt_text)
    assert "WEBVTT" not in srt_text
    assert "00:00:03,000 --> 00:00:03,500" in srt_text, "SRT writes a comma"
    assert [(round(c["start"], 3), c["text"]) for c in srt] == [
        (round(c["start"], 3), c["text"]) for c in vtt
    ]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_clips_are_cut_side_by_side(deck, server, tmp_path, no_libreoffice, monkeypatch):
    """--max-workers has to mean something for the cut as well, not only the voice."""
    import threading

    open_now = [0]
    seen = [0]
    lock = threading.Lock()
    real = core.create_slide_video

    def counting(*args, **kwargs):
        with lock:
            open_now[0] += 1
            seen[0] = max(seen[0], open_now[0])
        try:
            return real(*args, **kwargs)
        finally:
            with lock:
                open_now[0] -= 1

    monkeypatch.setattr(core, "create_slide_video", counting)
    out = core.make_video(deck, tmp_path / "deck.mp4", max_workers=4, **_options(server))
    assert get_video_duration(out) > 0
    assert seen[0] > 1, "the clips were cut one after another"


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_one_worker_still_cuts_every_clip(deck, server, tmp_path, no_libreoffice):
    work = tmp_path / "work"
    core.make_video(
        deck, tmp_path / "deck.mp4", max_workers=1, work_dir=str(work), **_options(server)
    )
    assert sorted(p.name for p in work.glob("clip_0*.mp4")) == [
        f"clip_{i:03d}.mp4" for i in range(4)
    ]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_speak_step_counts_only_the_chosen_slides(deck, server, tmp_path, no_libreoffice):
    """The progress bar of the page must not jump backwards or claim too many."""
    seen = []
    core.make_video(
        deck, tmp_path / "deck.mp4", slides=[0, 2],
        progress=lambda step, done, total: seen.append((step, done, total)),
        **_options(server),
    )
    speak = [row for row in seen if row[0] == "speak"]
    assert [row[2] for row in speak] == [2] * len(speak)
    assert [row[1] for row in speak] == [0, 1, 2]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_subtitle_step_reports_every_clip(deck, server, tmp_path, no_libreoffice):
    """A step that can wait for minutes has to show that it is moving."""
    seen = []
    core.make_video(
        deck, tmp_path / "deck.mp4",
        progress=lambda step, done, total: seen.append((step, done, total)),
        **_options(server, subtitles=True, stt_model="whisper"),
    )
    rows = [row for row in seen if row[0] == "subtitles"]
    # Four slides plus the notice clip at each end.
    assert rows[0] == ("subtitles", 0, 6)
    assert sorted(row[1] for row in rows) == [0, 1, 2, 3, 4, 5, 6, 6]


def test_the_subtitle_step_has_a_time_limit():
    from pptx_screencast import config

    assert config.STT_TIMEOUT > 0
    settings = config.resolve(
        base_url="http://127.0.0.1:1/v1", model="chat", require_voice=False
    )
    assert settings.stt_timeout == config.STT_TIMEOUT
    settings = config.resolve(
        base_url="http://127.0.0.1:1/v1", model="chat", stt_timeout=60.0, require_voice=False
    )
    assert settings.stt_timeout == 60.0
