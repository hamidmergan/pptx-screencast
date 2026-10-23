"""Settings come from arguments, then from the environment, then from defaults."""

import pytest

from pptx_screencast import config
from pptx_screencast.errors import ConfigError


def test_missing_base_url_and_model_are_named():
    with pytest.raises(ConfigError) as info:
        config.resolve()
    message = str(info.value)
    assert "--base-url" in message
    assert "--model" in message


def test_voice_is_only_required_when_speaking():
    settings = config.resolve(base_url="http://x/v1", model="chat", require_voice=False)
    assert settings.voice == ""


def test_speech_route_falls_back_to_the_chat_server():
    settings = config.resolve(
        base_url="http://x/v1", model="chat", tts_model="tts", voice="alloy"
    )
    assert settings.tts_base_url == "http://x/v1"
    assert settings.stt_base_url == "http://x/v1"


def test_speech_route_can_have_its_own_server():
    settings = config.resolve(
        base_url="http://x/v1", model="chat", voice="alloy",
        tts_base_url="http://y/v1", tts_model="tts", tts_api_key="secret",
    )
    assert settings.tts_base_url == "http://y/v1"
    assert settings.tts_api_key == "secret"
    assert settings.api_key == config.PLACEHOLDER_API_KEY


def test_environment_fills_the_gaps(monkeypatch):
    monkeypatch.setenv("PPTX_SCREENCAST_BASE_URL", "http://env/v1")
    monkeypatch.setenv("PPTX_SCREENCAST_MODEL", "env-chat")
    monkeypatch.setenv("PPTX_SCREENCAST_TTS_MODEL", "env-tts")
    monkeypatch.setenv("PPTX_SCREENCAST_VOICE", "nova")
    monkeypatch.setenv("PPTX_SCREENCAST_SUBTITLES", "true")
    settings = config.resolve()
    assert settings.base_url == "http://env/v1"
    assert settings.voice == "nova"
    assert settings.subtitles is True


def test_an_invalid_number_in_the_environment_is_reported(monkeypatch):
    monkeypatch.setenv("PPTX_SCREENCAST_RESOLUTION", "high")
    with pytest.raises(ConfigError) as info:
        config.resolve(base_url="http://x/v1", model="chat", require_voice=False)
    assert "PPTX_SCREENCAST_RESOLUTION" in str(info.value)


def test_without_a_recognition_model_there_are_no_subtitles():
    settings = config.resolve(base_url="http://x/v1", model="chat", require_voice=False)
    assert settings.has_stt is False
    assert config.resolve(
        base_url="http://x/v1", model="chat", stt_model="whisper", require_voice=False
    ).has_stt is True


def test_burn_in_without_subtitles_is_refused():
    with pytest.raises(ConfigError):
        config.resolve(
            base_url="http://x/v1", model="chat", require_voice=False, burn_in=True
        )


def test_values_must_be_positive():
    with pytest.raises(ConfigError):
        config.resolve(base_url="http://x/v1", model="chat", require_voice=False, resolution=0)
