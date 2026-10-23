"""What the package root offers, so nothing useful is only reachable inside."""

import pptx_screencast


def test_everything_named_in_all_is_really_there():
    for name in pptx_screencast.__all__:
        assert hasattr(pptx_screencast, name), name


def test_the_calls_a_tool_is_built_from_are_exported():
    for name in ("make_video", "write_script", "build_scripts"):
        assert callable(getattr(pptx_screencast, name))


def test_the_settings_are_exported():
    settings = pptx_screencast.resolve(
        base_url="http://127.0.0.1:1/v1", model="chat", require_voice=False
    )
    assert isinstance(settings, pptx_screencast.Settings)
    assert isinstance(pptx_screencast.env_defaults(), dict)


def test_the_subtitle_helpers_are_exported():
    """build_subtitle_srt and vtt_to_cues had no call site in the pipeline."""
    segments = [[{"start": 0.0, "end": 0.5, "text": "Hello"}]]
    srt = pptx_screencast.build_subtitle_srt(segments, [3.0])
    vtt = pptx_screencast.build_subtitle_vtt(segments, [3.0])
    assert "00:00:00,000 --> 00:00:00,500" in srt
    assert pptx_screencast.vtt_to_cues(vtt)[0]["text"] == "Hello"
    assert pptx_screencast.vtt_to_srt(vtt) == srt


def test_the_naming_and_script_helpers_are_exported():
    assert pptx_screencast.build_artifact_stem("deck").startswith("deck_")
    assert pptx_screencast.numbered_headings("## Slide 1\n\n## Slide 2\n") == [1, 2]


def test_the_version_is_a_string():
    assert isinstance(pptx_screencast.__version__, str)
