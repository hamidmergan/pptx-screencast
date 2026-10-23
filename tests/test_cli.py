"""The command line is a thin wrapper, so it mostly has to refuse well."""

import pytest
from PIL import Image

from pptx_screencast import cli, core
from pptx_screencast.script_file import parse_script_file, write_script_file


@pytest.fixture
def deck(tmp_path):
    from _pptx_fixtures import notes_pptx

    path = tmp_path / "deck.pptx"
    path.write_bytes(notes_pptx(["Note one.", "Note two."]))
    return path


@pytest.fixture
def no_libreoffice(monkeypatch):
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


def _model(server):
    return ["--base-url", server.base_url, "--model", "chat"]


# -- What the command line refuses --

def test_without_a_file_it_asks_for_one(capsys):
    assert cli.main([]) == 2
    assert "presentation" in capsys.readouterr().err


def test_a_missing_file_is_named(capsys, tmp_path):
    assert cli.main([str(tmp_path / "nope.pptx")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_notes_and_a_script_file_cannot_be_combined(capsys, deck, tmp_path):
    script = write_script_file(["a", "b"], tmp_path / "s.md")
    code = cli.main([str(deck), "--notes", "--from-script", str(script)])
    assert code == 2
    assert "not both" in capsys.readouterr().err


def test_writing_and_reading_a_script_cannot_be_combined(capsys, deck, tmp_path):
    script = write_script_file(["a", "b"], tmp_path / "s.md")
    code = cli.main([str(deck), "--script-only", "--from-script", str(script)])
    assert code == 2
    assert "--script-only" in capsys.readouterr().err


def test_burn_in_needs_subtitles(capsys, deck):
    assert cli.main([str(deck), "--burn-in"]) == 2
    assert "--subtitles" in capsys.readouterr().err


def test_missing_settings_end_in_a_clear_message(capsys, deck):
    assert cli.main([str(deck), "--script-only"]) == 1
    assert "--base-url" in capsys.readouterr().err


def test_a_broken_deck_ends_in_a_message_and_not_a_traceback(capsys, tmp_path, server):
    broken = tmp_path / "broken.pptx"
    broken.write_bytes(b"this is not a zip file")
    code = cli.main([str(broken), "--script-only", *_model(server)])
    assert code == 1
    assert "could not be read" in capsys.readouterr().err


def test_a_bad_slide_range_is_named(capsys, deck, server):
    code = cli.main([str(deck), "--slides", "five", *_model(server), "--voice", "alloy",
                     "--tts-model", "tts"])
    assert code == 1
    assert "slide number" in capsys.readouterr().err


# -- What it does --

def test_script_only_writes_a_markdown_file(capsys, deck, server, tmp_path):
    out = tmp_path / "deck.md"
    assert cli.main([str(deck), "--script-only", "-o", str(out), *_model(server)]) == 0
    assert out.exists()
    assert len(parse_script_file(out.read_text(encoding="utf-8"))) == 2
    assert capsys.readouterr().out.strip() == str(out)


def test_notes_as_the_script_reach_the_file(deck, server, tmp_path):
    out = tmp_path / "deck.md"
    cli.main([str(deck), "--script-only", "--notes", "-o", str(out), *_model(server)])
    assert parse_script_file(out.read_text(encoding="utf-8")) == ["Note one.", "Note two."]
    assert server.count("chat") == 0


def test_translate_goes_through_the_chat_model(deck, server, tmp_path):
    out = tmp_path / "deck.md"
    cli.main([str(deck), "--script-only", "--notes", "--translate", "German",
              "-o", str(out), *_model(server)])
    assert parse_script_file(out.read_text(encoding="utf-8"))[0].startswith("[translated]")


def test_a_video_is_built_and_its_path_printed(capsys, deck, server, tmp_path, no_libreoffice):
    out = tmp_path / "deck.mp4"
    code = cli.main([str(deck), "-o", str(out), "--voice", "alloy", "--tts-model", "tts",
                     "-q", *_model(server)])
    assert code == 0
    assert out.exists()
    assert capsys.readouterr().out.strip() == str(out)


def test_slides_are_counted_from_one_on_the_command_line(deck, server, tmp_path, no_libreoffice):
    out = tmp_path / "deck.mp4"
    cli.main([str(deck), "-o", str(out), "--slides", "2", "--voice", "alloy",
              "--tts-model", "tts", "-q", *_model(server)])
    assert server.count("speech") == 1


def test_the_progress_goes_to_stderr(capsys, deck, server, tmp_path, no_libreoffice):
    cli.main([str(deck), "-o", str(tmp_path / "deck.mp4"), "--voice", "alloy",
              "--tts-model", "tts", *_model(server)])
    assert "speak:" in capsys.readouterr().err


def test_quiet_keeps_the_progress_out(capsys, deck, server, tmp_path, no_libreoffice):
    cli.main([str(deck), "-o", str(tmp_path / "deck.mp4"), "--voice", "alloy",
              "--tts-model", "tts", "-q", *_model(server)])
    assert "speak:" not in capsys.readouterr().err


# -- The help text --

def test_the_help_is_english_and_names_the_example():
    text = cli._parser().format_help()
    assert "OpenAI-compatible" in text
    assert "deck.pptx" in text
    for flag in ("--voice", "--script-only", "--from-script", "--notes",
                 "--translate", "--subtitles", "--burn-in", "--slides"):
        assert flag in text


def test_the_version_is_reported(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert "pptx-screencast" in capsys.readouterr().out


def test_the_fps_flag_reaches_the_settings(deck, server, tmp_path, no_libreoffice, monkeypatch):
    seen = {}
    real = core.config.resolve

    def spy(**kwargs):
        resolved = real(**kwargs)
        seen["fps"] = resolved.fps
        return resolved

    monkeypatch.setattr(core.config, "resolve", spy)
    cli.main([str(deck), "-o", str(tmp_path / "out.mp4"), "--fps", "18",
              *_model(server), "--voice", "alloy", "--tts-model", "tts", "-q"])
    assert seen["fps"] == 18


def test_the_glossary_flag_reaches_the_prompt(deck, server, tmp_path):
    terms = tmp_path / "terms.txt"
    terms.write_text("Rechenzentrum = data centre\n", encoding="utf-8")
    code = cli.main([str(deck), "--script-only", "-o", str(tmp_path / "deck.md"),
                     "--glossary", str(terms), *_model(server)])
    assert code == 0
    system = [r for r in server.requests if r["route"] == "chat"][0]["body"]["messages"][0]
    assert "Rechenzentrum → data centre" in system["content"]


def test_a_broken_glossary_is_named(capsys, deck, server, tmp_path):
    terms = tmp_path / "terms.txt"
    terms.write_text("Rechenzentrum data centre\n", encoding="utf-8")
    code = cli.main([str(deck), "--script-only", "--glossary", str(terms), *_model(server)])
    assert code == 1
    assert "separator" in capsys.readouterr().err
    assert server.count("chat") == 0


def test_the_glossary_also_reaches_the_translation(deck, server, tmp_path):
    terms = tmp_path / "terms.json"
    terms.write_text('{"Folie": "slide"}', encoding="utf-8")
    cli.main([str(deck), "--script-only", "-o", str(tmp_path / "deck.md"), "--notes",
              "--translate", "French", "--glossary", str(terms), *_model(server)])
    system = [r for r in server.requests if r["route"] == "chat"][0]["body"]["messages"][0]
    assert "You translate" in system["content"]
    assert "Folie → slide" in system["content"]
