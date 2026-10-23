"""Work directory and output names."""

from datetime import datetime
from pathlib import Path

from pptx_screencast.naming import build_artifact_stem, readable_stem, translate_stem
from pptx_screencast.paths import free_path, safe_stem, work_dir


def test_a_stem_keeps_only_safe_characters():
    assert safe_stem("my deck/../sales?.pptx") == "sales"
    assert safe_stem("Lecture 01.pptx") == "Lecture 01"


def test_an_empty_name_falls_back():
    assert safe_stem("   .pptx") == "screencast"


def test_a_generated_name_never_overwrites(tmp_path):
    target = tmp_path / "deck.mp4"
    target.write_bytes(b"x")
    assert free_path(target).name == "deck (1).mp4"
    free_path(target).write_bytes(b"x")
    assert free_path(target).name == "deck (2).mp4"


def test_a_free_name_is_returned_unchanged(tmp_path):
    assert free_path(tmp_path / "deck.mp4").name == "deck.mp4"


def test_a_temporary_work_directory_is_removed():
    with work_dir() as folder:
        assert folder.is_dir()
        (folder / "a.txt").write_text("x")
    assert not folder.exists()


def test_a_configured_work_directory_stays(tmp_path):
    target = tmp_path / "work" / "deep"
    with work_dir(str(target)) as folder:
        assert folder == target
        (folder / "a.txt").write_text("x")
    assert (target / "a.txt").exists()


def test_the_timestamp_is_appended():
    stem = build_artifact_stem("deck", datetime(2026, 3, 4, 9, 7))
    assert stem == "deck_2026-03-04_0907"


def test_an_empty_stem_gets_a_name():
    assert build_artifact_stem("  ").startswith("screencast_")


def test_a_stem_is_made_readable_before_translating():
    assert readable_stem("my_long-deck") == "my long deck"


def test_the_stem_goes_through_the_translator():
    calls = []

    def translator(text, target_lang):
        calls.append((text, target_lang))
        return "mein langes Deck"

    assert translate_stem("my_long_deck.pptx", "de", translator) == "mein_langes_Deck"
    assert calls == [("my long deck", "de")]


def test_a_failed_translation_keeps_the_original_stem():
    def translator(text, target_lang):
        raise RuntimeError("the server is away")

    assert translate_stem("my_deck.pptx", "de", translator) == "my_deck"


def test_without_a_translator_the_stem_stays():
    assert translate_stem("my_deck.pptx", "de") == "my_deck"
    assert translate_stem("my_deck.pptx", "") == "my_deck"


def test_a_relative_work_directory_becomes_absolute(tmp_path, monkeypatch):
    """ffmpeg reads concat entries relative to the list file, so paths must be absolute."""
    monkeypatch.chdir(tmp_path)
    with work_dir("work") as folder:
        assert folder.is_absolute()
        assert folder == (tmp_path / "work").resolve()


def test_a_relative_temporary_work_directory_is_absolute_too():
    with work_dir() as folder:
        assert folder.is_absolute()
