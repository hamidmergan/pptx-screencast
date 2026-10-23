"""Where the narration comes from: the model, the notes or a script file."""

import pytest
from _fake_llm import ScriptClient, slides

from pptx_screencast.errors import ScriptError
from pptx_screencast.generation import (
    check_count,
    generate_all_scripts,
    scripts_from_file,
    scripts_from_notes,
)
from pptx_screencast.script_file import write_script_file


def test_the_model_writes_one_script_per_slide():
    client = ScriptClient(["Script one.\n|||\nScript two.\n|||\nScript three."])
    assert generate_all_scripts(slides(3), client) == [
        "Script one.", "Script two.", "Script three."
    ]


def test_a_refused_provider_becomes_a_script_error():
    client = ScriptClient([RuntimeError("Error code: 401 - invalid key")] * 4)
    with pytest.raises(ScriptError) as info:
        generate_all_scripts(slides(2), client)
    assert "Script generation failed" in str(info.value)


def test_notes_become_the_narration():
    assert scripts_from_notes([" one ", "", "three"]) == ["one", "", "three"]


def test_notes_are_padded_to_the_slide_count():
    assert scripts_from_notes(["one"], count=3) == ["one", "", ""]


def test_a_deck_without_any_note_is_refused():
    with pytest.raises(ScriptError) as info:
        scripts_from_notes(["", "  "])
    assert "--notes" in str(info.value)


def test_a_script_file_is_read_back(tmp_path):
    path = write_script_file(["one", "two"], tmp_path / "deck.md")
    assert scripts_from_file(path, count=2) == ["one", "two"]


def test_a_wrong_count_is_caught():
    with pytest.raises(ScriptError) as info:
        check_count(["one", "two"], 3)
    assert "3 slide(s)" in str(info.value)


def test_a_matching_count_passes_through():
    assert check_count(["one", "two"], 2) == ["one", "two"]
