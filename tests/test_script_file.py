"""The script file is written, corrected by hand and read back."""

import pytest

from pptx_screencast.errors import ScriptError
from pptx_screencast.script_file import (
    numbered_headings,
    parse_script_file,
    read_script_file,
    render_script_file,
    write_script_file,
)

SCRIPTS = [
    "Welcome to this short tour.",
    "The first point is the simplest one.",
    "",
    "And that is all for today.",
]


def test_round_trip_keeps_every_slide():
    assert parse_script_file(render_script_file(SCRIPTS)) == SCRIPTS


def test_round_trip_through_a_file(tmp_path):
    path = write_script_file(SCRIPTS, tmp_path / "deck.md", title="deck")
    assert read_script_file(path, count=4) == SCRIPTS


def test_a_title_is_not_spoken(tmp_path):
    path = write_script_file(SCRIPTS, tmp_path / "deck.md", title="My deck")
    assert path.read_text(encoding="utf-8").startswith("# My deck")
    assert read_script_file(path)[0] == SCRIPTS[0]


def test_an_empty_slide_keeps_its_place():
    text = render_script_file(["one", "", "three"])
    assert parse_script_file(text) == ["one", "", "three"]


def test_headings_are_numbered_from_one():
    text = render_script_file(["one", "two"])
    assert "## Slide 1" in text
    assert "## Slide 2" in text
    assert numbered_headings(text) == [1, 2]


def test_a_hand_written_file_with_other_headings_is_accepted():
    text = "# notes\n\n### Intro\n\nHello.\n\n### Outlook\n\nGoodbye.\n"
    assert parse_script_file(text) == ["Hello.", "Goodbye."]


def test_several_paragraphs_stay_in_one_script():
    text = "## Slide 1\n\nFirst sentence.\n\nSecond paragraph.\n"
    assert parse_script_file(text) == ["First sentence.\n\nSecond paragraph."]


def test_a_file_without_a_heading_is_refused():
    with pytest.raises(ScriptError) as info:
        parse_script_file("Just some text without a heading.")
    assert "heading" in str(info.value)


def test_a_file_with_only_a_title_is_refused():
    with pytest.raises(ScriptError):
        parse_script_file("# deck\n")


def test_a_wrong_slide_count_is_named(tmp_path):
    path = write_script_file(["one", "two"], tmp_path / "deck.md")
    with pytest.raises(ScriptError) as info:
        read_script_file(path, count=3)
    assert "2 slide(s)" in str(info.value)
    assert "3" in str(info.value)


def test_a_missing_file_is_reported(tmp_path):
    with pytest.raises(ScriptError):
        read_script_file(tmp_path / "nope.md")


def test_the_file_ends_with_one_newline():
    text = render_script_file(["one"])
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
