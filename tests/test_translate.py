"""Translating a finished narration with the chat model."""

import pytest
from _fake_llm import ScriptClient

from pptx_screencast.generation import translate_scripts


def test_the_target_language_is_named_in_the_prompt():
    client = ScriptClient(["Bonjour."])
    assert client.translate_text("Hello.", "French") == "Bonjour."
    assert "Output MUST be in French" in client.calls[0][0]["content"]


def test_empty_text_costs_no_request():
    client = ScriptClient([])
    assert client.translate_text("", "French") == ""
    assert client.translate_text("   ", "French") == "   "
    assert client.calls == []


def test_without_a_target_language_nothing_is_sent():
    client = ScriptClient([])
    assert client.translate_text("Hello.", "") == "Hello."
    assert client.calls == []


def test_a_batch_keeps_its_order_and_its_empty_slides():
    client = ScriptClient(["Eins.", "Drei."])
    result = client.translate_batch(["One.", "", "Three."], "German")
    assert result == ["Eins.", "", "Drei."]


def test_a_failed_slide_keeps_its_original():
    client = ScriptClient(["Eins.", RuntimeError("provider gone"), "Drei."])
    result = client.translate_batch(["One.", "Two.", "Three."], "German")
    assert result == ["Eins.", "Two.", "Drei."]


def test_a_missing_answer_is_an_error():
    client = ScriptClient([None])
    with pytest.raises(RuntimeError):
        client.translate_text("Hello.", "German")


def test_the_helper_passes_the_whole_deck_through():
    client = ScriptClient(["Eins.", "Zwei."])
    assert translate_scripts(["One.", "Two."], "German", client) == ["Eins.", "Zwei."]


def test_the_helper_does_nothing_without_a_language():
    client = ScriptClient([])
    assert translate_scripts(["One."], "", client) == ["One."]
    assert client.calls == []
