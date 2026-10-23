"""The whole way from a deck to the finished MP4.

LibreOffice is not needed here: the slide rendering is replaced by plain
pictures, everything after it is the real code with real ffmpeg.
"""

import shutil

import pytest
from PIL import Image

from pptx_screencast import core
from pptx_screencast.errors import ScriptError, SlideError
from pptx_screencast.script_file import parse_script_file, write_script_file
from pptx_screencast.video import get_video_duration

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


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
