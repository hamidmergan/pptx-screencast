"""The notice slide at the start and the end of the video."""

from pathlib import Path

from PIL import Image

from pptx_screencast.outro import (
    NOTICE_TEXT,
    create_outro_image,
    frame_clips,
    get_image_dimensions,
)


def test_the_notice_slide_has_the_size_of_the_deck(tmp_path):
    path = create_outro_image(640, 480, tmp_path / "notice.png")
    assert get_image_dimensions(path) == (640, 480)


def test_the_notice_slide_is_not_blank(tmp_path):
    path = create_outro_image(640, 480, tmp_path / "notice.png")
    with Image.open(path) as img:
        colours = img.convert("L").getcolors(maxcolors=256)
    assert colours is not None
    assert len(colours) > 1, "the text has to be visible on the slide"


def test_a_long_text_is_wrapped_and_stays_inside(tmp_path):
    long = "This video was created with AI assistance and nobody checked every word of it."
    path = create_outro_image(320, 240, tmp_path / "notice.png", text=long)
    assert get_image_dimensions(path) == (320, 240)


def test_the_notice_frames_the_clips():
    clips = [Path("a.mp4"), Path("b.mp4")]
    notice = Path("notice.mp4")
    framed, speech = frame_clips(clips, [True, False], notice)
    assert framed == [notice, *clips, notice]
    assert speech == [False, True, False, False]


def test_without_a_notice_nothing_is_added():
    clips = [Path("a.mp4")]
    framed, speech = frame_clips(clips, [True], None)
    assert framed == clips
    assert speech == [True]


def test_the_notice_text_says_what_made_the_video():
    assert "AI" in NOTICE_TEXT
