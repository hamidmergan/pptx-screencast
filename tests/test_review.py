"""Which slides a translation handed back unchanged."""

from _fake_llm import ScriptClient

from pptx_screencast.generation import translate_scripts
from pptx_screencast.review import MIN_WORDS, find_unchanged_slides


def test_an_unchanged_slide_is_named():
    before = ["This slide shows the measured result.", "Another long enough sentence here."]
    after = ["This slide shows the measured result.", "Ein anderer langer Satz steht hier."]
    assert find_unchanged_slides(before, after) == [0]


def test_a_short_text_is_not_worth_reporting():
    """A heading of two words is often the same in both languages."""
    assert find_unchanged_slides(["Results"], ["Results"]) == []
    assert find_unchanged_slides([""], [""]) == []


def test_the_word_floor_can_be_moved():
    assert find_unchanged_slides(["one two"], ["one two"], min_words=2) == [0]


def test_whitespace_alone_is_not_a_change():
    long_text = " ".join(["word"] * MIN_WORDS)
    assert find_unchanged_slides([long_text], [f"  {long_text}  "]) == [0]


def test_a_missing_counterpart_is_skipped():
    long_text = " ".join(["word"] * MIN_WORDS)
    assert find_unchanged_slides([long_text, long_text], [long_text]) == [0]


def test_the_translation_warns_about_the_slides_it_left_alone(caplog):
    long_text = "This slide shows the measured result of the second run."
    client = ScriptClient([long_text, "Ein ganz anderer Satz."])
    with caplog.at_level("WARNING"):
        translate_scripts([long_text, long_text], "German", client)
    assert "slide(s) 1" in caplog.text


def test_a_fully_translated_deck_warns_about_nothing(caplog):
    long_text = "This slide shows the measured result of the second run."
    client = ScriptClient(["Erster Satz hier.", "Zweiter Satz hier."])
    with caplog.at_level("WARNING"):
        translate_scripts([long_text, long_text], "German", client)
    assert "exactly as they were" not in caplog.text
