"""A fixed term mapping, for the narration the model writes and for the translation."""

import pytest
from _fake_llm import ScriptClient

from pptx_screencast.errors import ScriptError
from pptx_screencast.generation import translate_scripts
from pptx_screencast.glossary import glossary_hint, parse_glossary, read_glossary


# -- Reading a glossary --

def test_a_line_per_term_is_read():
    assert parse_glossary("Rechenzentrum = data centre\nFolie = slide\n") == {
        "Rechenzentrum": "data centre",
        "Folie": "slide",
    }


def test_an_arrow_and_a_tab_work_as_well():
    assert parse_glossary("Rechenzentrum -> data centre") == {"Rechenzentrum": "data centre"}
    assert parse_glossary("Folie\tslide") == {"Folie": "slide"}


def test_comments_and_blank_lines_are_skipped():
    raw = "# the terms of this deck\n\nFolie = slide\n"
    assert parse_glossary(raw) == {"Folie": "slide"}


def test_a_json_object_is_read():
    assert parse_glossary('{"Folie": "slide"}') == {"Folie": "slide"}


def test_broken_json_is_named():
    with pytest.raises(ScriptError) as info:
        parse_glossary('{"Folie": }')
    assert "valid JSON" in str(info.value)


def test_a_json_list_is_refused():
    with pytest.raises(ScriptError):
        parse_glossary('["Folie"]')


def test_a_line_without_a_separator_is_named():
    with pytest.raises(ScriptError) as info:
        parse_glossary("Folie slide")
    assert "separator" in str(info.value)


def test_a_line_without_a_replacement_is_named():
    with pytest.raises(ScriptError) as info:
        parse_glossary("Folie = ")
    assert "no replacement" in str(info.value)


def test_an_empty_glossary_file_is_refused(tmp_path):
    path = tmp_path / "terms.txt"
    path.write_text("# nothing but a comment\n", encoding="utf-8")
    with pytest.raises(ScriptError) as info:
        read_glossary(path)
    assert "holds no term" in str(info.value)


def test_a_missing_glossary_file_is_named(tmp_path):
    with pytest.raises(ScriptError) as info:
        read_glossary(tmp_path / "nope.txt")
    assert "could not be read" in str(info.value)


def test_a_glossary_file_is_read(tmp_path):
    path = tmp_path / "terms.txt"
    path.write_text("Folie = slide\n", encoding="utf-8")
    assert read_glossary(path) == {"Folie": "slide"}


# -- Where it ends up --

def test_the_hint_names_every_term():
    hint = glossary_hint({"Folie": "slide"})
    assert "Folie → slide" in hint


def test_without_terms_there_is_no_hint():
    assert glossary_hint(None) == ""
    assert glossary_hint({}) == ""


def test_the_translation_carries_the_glossary():
    """The narration honours the terms, so the translation has to as well."""
    client = ScriptClient(["Bonjour."])
    client.translate_text("Hello.", "French", {"data centre": "centre de donnees"})
    assert "data centre → centre de donnees" in client.calls[0][0]["content"]


def test_a_translated_deck_carries_the_glossary():
    client = ScriptClient(["Eins.", "Zwei."])
    translate_scripts(["One.", "Two."], "German", client, glossary={"slide": "Folie"})
    assert all("slide → Folie" in call[0]["content"] for call in client.calls)


def test_a_translation_without_a_glossary_sends_the_plain_prompt():
    client = ScriptClient(["Bonjour."])
    client.translate_text("Hello.", "French")
    assert "terminology" not in client.calls[0][0]["content"]


def test_the_generated_narration_carries_the_glossary():
    client = ScriptClient(["Slide one.", "Slide two."])
    client.generate_scripts_batch(["A", "B"], {"Folie": "slide"})
    assert "Folie → slide" in client.calls[0][0]["content"]
