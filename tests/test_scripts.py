"""The slide to script mapping has to hold for faulty batches too."""

import pytest
from _fake_llm import ScriptClient, slides

from pptx_screencast import scripts as module
from pptx_screencast.scripts import (
    build_length_and_format_rules,
    find_misaligned,
    is_blank_script,
)


@pytest.fixture(autouse=True)
def _no_retry_delay(monkeypatch):
    """The second attempt waits 5 seconds in operation, not in the test."""
    monkeypatch.setattr(module, "_BATCH_RETRY_DELAY", 0.0)


# -- One script per slide, whatever comes back --

def test_clean_batch_maps_one_to_one():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    result = client.generate_scripts_batch(slides(3), add_greeting=False, add_closing=False)
    assert result == ["Script A", "Script B", "Script C"]


def test_trailing_delimiter_is_tolerated():
    """A separator at the end is harmless and must not count as an error."""
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C\n|||"])
    result = client.generate_scripts_batch(slides(3), add_greeting=False, add_closing=False)
    assert result == ["Script A", "Script B", "Script C"]


def test_missing_delimiter_falls_back_to_one_call_per_slide():
    """Instead of shifting, every slide is generated on its own, which cannot go wrong."""
    client = ScriptClient([
        "Script A and Script B together\n|||\nScript C",  # one separator missing
        "Script A and Script B together\n|||\nScript C",  # the repeat is wrong as well
        "Script A",
        "Script B",
        "Script C",
    ])
    result = client.generate_scripts_batch(slides(3), add_greeting=False, add_closing=False)
    assert result == ["Script A", "Script B", "Script C"]


def test_failed_single_slide_only_costs_that_slide():
    """If a slide fails on its own it stays empty, the others do not."""
    client = ScriptClient([
        "only one part",                  # batch, first attempt
        "only one part",                  # batch, second attempt
        "Script A",                       # slide 1 on its own
        RuntimeError("provider gone"),    # slide 2 on its own
        "Script C",                       # slide 3 on its own
    ])
    result = client.generate_scripts_batch(slides(3), add_greeting=False, add_closing=False)
    assert result[0] == "Script A"
    assert result[1] == ""
    assert result[2] == "Script C"


def test_short_last_batch_keeps_its_length_on_failure():
    """The last batch is often shorter, if it fails the list must not grow."""
    client = ScriptClient([RuntimeError("gone")] * 20, batch_size=3)
    result = client.generate_scripts_batch(slides(4), add_greeting=False, add_closing=False)
    assert len(result) == 4


@pytest.mark.parametrize("count", [1, 2, 5, 8])
def test_slide_count_is_always_preserved(count):
    client = ScriptClient(["broken answer without a separator"] * 40)
    result = client.generate_scripts_batch(slides(count), add_greeting=False, add_closing=False)
    assert len(result) == count


# -- The rules that go into the system prompt --

def _rules() -> str:
    return build_length_and_format_rules(3, "EN-US", "", "", 1500, 2000)


def test_length_rule_is_a_ceiling_not_a_range():
    """A fixed range forces the model to repeat itself on thin slides."""
    rules = _rules()
    assert "between 1500 and 2000 characters" not in rules
    assert "Never write more than 2000 characters" in rules


def test_padding_is_forbidden_explicitly():
    rules = _rules().lower()
    assert "never repeat" in rules
    assert "stop as soon as the slide is covered" in rules


def test_short_slides_are_allowed_to_stay_short():
    assert "one line of content" in _rules()


def test_delimiter_contract_is_still_stated():
    rules = _rules()
    assert "|||" in rules
    assert "Separate the 3 scripts" in rules


def test_prompt_demands_a_script_for_every_slide_with_content():
    """The rule against repetition must not become a licence to stay silent."""
    rules = _rules()
    assert "at least one sentence" in rules
    assert "similar to the previous one" in rules
    assert "not a placeholder word" in rules


# -- No silent slide and no placeholder read aloud --

LONG = "This slide introduces the study series and its main findings."


def test_slide_with_text_never_stays_silent():
    """Slide 2 has content but comes back empty, it is redone on its own."""
    client = ScriptClient([
        f"{LONG}\n|||\n\n|||\n{LONG}",                        # middle slide empty
        "Now we look at who the affected children turn to.",  # the repeat
    ])
    result = client.generate_scripts_batch(
        ["Slide text one", "Slide text two", "Slide text three"],
        add_greeting=False, add_closing=False,
    )
    assert result[1].startswith("Now we look at")
    assert len(client.calls) == 2, "exactly one repeat, not the whole batch"


def test_placeholder_is_treated_as_missing():
    """'(Empty)' is not a script, it would otherwise be read aloud."""
    client = ScriptClient([
        f"{LONG}\n|||\n(Empty)\n|||\n{LONG}",
        "The chart shows the contact persons children choose.",
    ])
    result = client.generate_scripts_batch(
        ["one", "two", "three"], add_greeting=False, add_closing=False
    )
    assert "Empty" not in result[1]
    assert result[1].startswith("The chart shows")


def test_placeholder_never_reaches_the_video_even_if_retry_fails():
    """If the second attempt also returns only a placeholder, better stay silent."""
    client = ScriptClient([f"{LONG}\n|||\n(Empty)\n|||\n{LONG}", "(empty)"])
    result = client.generate_scripts_batch(
        ["one", "two", "three"], add_greeting=False, add_closing=False
    )
    assert result[1] == ""


def test_truly_empty_slide_costs_no_extra_call():
    """A slide without text may stay empty, without asking the model."""
    client = ScriptClient([f"{LONG}\n|||\n\n|||\n{LONG}"])
    result = client.generate_scripts_batch(
        ["one", "", "three"], add_greeting=False, add_closing=False
    )
    assert result[1] == ""
    assert len(client.calls) == 1


def test_full_batch_is_untouched():
    client = ScriptClient([f"{LONG} A\n|||\n{LONG} B\n|||\n{LONG} C"])
    result = client.generate_scripts_batch(
        ["one", "two", "three"], add_greeting=False, add_closing=False
    )
    assert all(s.strip() for s in result)
    assert len(client.calls) == 1


@pytest.mark.parametrize("value", ["", "   ", "(Empty)", "[empty]", "-", "n/a", "(leer)", "..."])
def test_blank_detection_catches_placeholders_in_any_language(value):
    """Detection by length, not by a word list."""
    assert is_blank_script(value)


@pytest.mark.parametrize("value", [
    "This slide shows the results.",
    "Diese Folie zeigt die Ergebnisse.",
    "Cette diapositive montre les resultats.",
])
def test_real_sentences_are_not_blank(value):
    assert not is_blank_script(value)


# -- No script may end up on the wrong slide --

SLIDE_PICTURES = "Sample tasks"
SLIDE_NEWS_TEST = (
    "Current study by a research foundation on how to deal with news "
    "and information on the internet. Test subjects only achieved an average of "
    "13.3 out of a maximum of 30 points."
)
SLIDE_PROGRAMMES = (
    "Numerous programs and projects, especially for children and young people and "
    "older people. Comprehensive handout from a standards body: Digital Skills Toolkit."
)

SCRIPT_NEWS_TEST = (
    "A current study by a research foundation examines how people deal "
    "with news and information on the internet. Test subjects achieved 13.3 points."
)
SCRIPT_PROGRAMMES = (
    "There are numerous programs and projects for children and young people and for "
    "older people. A standards body provides a handout called the Digital Skills Toolkit."
)
SCRIPT_PICTURES = "This slide shows sample tasks on spotting advertisements in news feeds."


def test_a_real_offset_is_detected():
    shifted = [SCRIPT_NEWS_TEST, SCRIPT_PROGRAMMES, SCRIPT_PROGRAMMES]
    deck = [SLIDE_PICTURES, SLIDE_NEWS_TEST, SLIDE_PROGRAMMES]
    assert find_misaligned(shifted, deck) is not None


def test_a_matching_mapping_is_no_offset():
    matching = [SCRIPT_PICTURES, SCRIPT_NEWS_TEST, SCRIPT_PROGRAMMES]
    deck = [SLIDE_PICTURES, SLIDE_NEWS_TEST, SLIDE_PROGRAMMES]
    assert find_misaligned(matching, deck) is None


def test_a_shifted_batch_is_redone_slide_by_slide():
    client = ScriptClient([
        f"{SCRIPT_NEWS_TEST}\n|||\n{SCRIPT_PROGRAMMES}\n|||\n{SCRIPT_PROGRAMMES}",
        SCRIPT_PICTURES,
        SCRIPT_NEWS_TEST,
        SCRIPT_PROGRAMMES,
    ])
    result = client.generate_scripts_batch(
        [SLIDE_PICTURES, SLIDE_NEWS_TEST, SLIDE_PROGRAMMES],
        add_greeting=False, add_closing=False,
    )
    assert "sample tasks" in result[0].lower()
    assert "research foundation" in result[1]
    assert "Digital Skills Toolkit" in result[2]
    assert len(client.calls) == 4, "one batch, then three slides on their own"


def test_a_matching_batch_costs_no_extra_call():
    client = ScriptClient([
        f"{SCRIPT_PICTURES}\n|||\n{SCRIPT_NEWS_TEST}\n|||\n{SCRIPT_PROGRAMMES}",
    ])
    client.generate_scripts_batch(
        [SLIDE_PICTURES, SLIDE_NEWS_TEST, SLIDE_PROGRAMMES],
        add_greeting=False, add_closing=False,
    )
    assert len(client.calls) == 1


def test_a_slide_without_text_raises_no_false_alarm():
    """An empty slide has no content to measure anything against."""
    client = ScriptClient([f"{SCRIPT_NEWS_TEST}\n|||\n\n|||\n{SCRIPT_PROGRAMMES}"])
    result = client.generate_scripts_batch(
        [SLIDE_NEWS_TEST, "", SLIDE_PROGRAMMES],
        add_greeting=False, add_closing=False,
    )
    assert result[1] == ""
    assert len(client.calls) == 1


# -- No hard-wired closing remark on the last script --

def test_no_english_thank_you_when_closing_is_allowed():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    result = client.generate_scripts_batch(
        slides(3), add_greeting=False, add_closing=True, target_lang="DE"
    )
    assert result == ["Script A", "Script B", "Script C"]
    assert not any("thank you" in s.lower() for s in result)


def test_closing_off_forbids_the_phrase_in_the_prompt():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    client.generate_scripts_batch(
        slides(3), add_greeting=False, add_closing=False, target_lang="DE"
    )
    system_prompt = client.calls[0][0]["content"]
    assert "Do not add any closing statement or thank-you." in system_prompt


def test_greeting_is_asked_for_on_the_first_slide_only():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    client.generate_scripts_batch(slides(3), add_greeting=True, add_closing=False)
    system_prompt = client.calls[0][0]["content"]
    user_message = client.calls[0][1]["content"]
    assert "[FIRST SLIDE]" in system_prompt
    assert user_message.count("[FIRST SLIDE") == 1


def test_the_target_language_reaches_the_prompt():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    client.generate_scripts_batch(slides(3), target_lang="FR")
    assert "Output MUST be in FR" in client.calls[0][0]["content"]


def test_material_is_offered_to_the_model():
    client = ScriptClient(["Script A\n|||\nScript B\n|||\nScript C"])
    client.generate_scripts_batch(
        slides(3), add_greeting=False, add_closing=False,
        materials=["", "a definition from the handout", ""],
    )
    user_message = client.calls[0][1]["content"]
    assert "[MATERIAL]" in user_message
    assert "a definition from the handout" in user_message
