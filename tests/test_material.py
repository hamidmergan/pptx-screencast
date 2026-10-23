"""Extra text per slide: cleaned of the batch separators and trimmed."""

import pytest
from _fake_llm import ScriptClient

from pptx_screencast.generation import generate_all_scripts
from pptx_screencast.material import (
    MATERIAL_CHARS,
    clean_material,
    material_slice,
    prepare_materials,
)


# -- The separator guard --

def test_a_batch_separator_cannot_come_in_through_the_material():
    """||| and === would shift every script of the batch by one slide."""
    assert "|||" not in clean_material("before ||| after")
    assert "===" not in clean_material("before\n===\nafter")


def test_plain_material_comes_through_unchanged():
    assert clean_material("  A definition and an example.  ") == "A definition and an example."


def test_line_ends_are_unified_and_long_gaps_collapsed():
    assert clean_material("a\r\nb\r\n\n\n\nc") == "a\nb\n\nc"


# -- The length guard --

def test_short_material_is_not_trimmed():
    assert material_slice("A short note.", 100) == "A short note."


def test_material_is_cut_at_a_sentence_end():
    text = "First sentence here. Second sentence here. Third sentence here."
    cut = material_slice(text, 45)
    assert cut == "First sentence here. Second sentence here."


def test_material_without_a_sentence_end_is_cut_at_a_word():
    cut = material_slice("alpha beta gamma delta epsilon zeta", 20)
    assert cut == "alpha beta gamma"
    assert len(cut) <= 20


def test_a_zero_limit_leaves_nothing():
    assert material_slice("anything", 0) == ""


# -- One entry per slide --

def test_the_entries_are_lined_up_with_the_slides():
    assert prepare_materials(["a note of some length"], 3) == ["a note of some length", "", ""]
    assert prepare_materials(["one", "two", "three"], 2) == ["one", "two"]


def test_without_material_there_is_none():
    assert prepare_materials(None, 3) is None
    assert prepare_materials([], 3) is None
    assert prepare_materials(["", "   "], 2) is None


def test_every_entry_is_cleaned_and_trimmed():
    prepared = prepare_materials(["x ||| y", "z" * (MATERIAL_CHARS + 50)], 2)
    assert "|||" not in prepared[0]
    assert len(prepared[1]) <= MATERIAL_CHARS


def test_the_trimming_is_logged(caplog):
    with caplog.at_level("INFO"):
        prepare_materials(["z" * (MATERIAL_CHARS + 50)], 1)
    assert "trimmed" in caplog.text


# -- Where it ends up --

def test_the_material_reaches_the_prompt():
    client = ScriptClient(["One.", "Two."])
    generate_all_scripts(
        ["Slide A", "Slide B"], client, materials=["The definition of A.", ""]
    )
    user = client.calls[0][1]["content"]
    assert "[MATERIAL]\nThe definition of A.\n[END MATERIAL]" in user


def test_a_separator_in_the_material_never_reaches_the_prompt():
    client = ScriptClient(["One.", "Two."])
    generate_all_scripts(
        ["Slide A", "Slide B"], client, materials=["bad ||| worse", ""]
    )
    user = client.calls[0][1]["content"]
    assert user.count("|||") == 0
    assert user.count("\n===\n") == 1, "only the separator between the two slides"


def test_without_material_the_prompt_has_no_material_rule():
    client = ScriptClient(["One.", "Two."])
    generate_all_scripts(["Slide A", "Slide B"], client)
    system = client.calls[0][0]["content"]
    assert "[MATERIAL]" not in system
    assert "Do NOT add any new information." in system


def test_with_material_the_prompt_says_how_to_use_it():
    client = ScriptClient(["One.", "Two."])
    generate_all_scripts(["Slide A", "Slide B"], client, materials=["A note on A.", ""])
    system = client.calls[0][0]["content"]
    assert "[MATERIAL]" in system
