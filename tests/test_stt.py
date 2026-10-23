"""Reading the word times back out of the finished audio."""

import pytest

from pptx_screencast import stt as module
from pptx_screencast.client import make_stt_client
from pptx_screencast.config import resolve


@pytest.fixture
def recogniser(server):
    settings = resolve(
        base_url=server.base_url, model="chat", stt_model="whisper", require_voice=False
    )
    return module.Recogniser(make_stt_client(settings), settings.stt_model)


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "slide.mp3"
    path.write_bytes(b"not really audio, the fake server does not look")
    return path


def test_the_segments_come_back_with_their_times(recogniser, audio, server):
    server.transcript_words = ["Hello", "world"]
    segments, language = recogniser.transcribe_verbose(str(audio))
    assert [s["text"] for s in segments] == ["Hello", "world"]
    assert segments[0]["start"] == 0.0
    assert segments[1]["start"] == 0.5


def test_a_busy_server_is_asked_again(recogniser, audio, server, monkeypatch):
    monkeypatch.setattr(module.Recogniser, "BACKOFFS", (0.0, 0.0))
    server.fail_times = 1
    server.status = 503
    segments, _ = recogniser.transcribe_verbose(str(audio))
    assert segments


def test_a_server_that_stays_down_raises(recogniser, audio, server, monkeypatch):
    monkeypatch.setattr(module.Recogniser, "BACKOFFS", (0.0,))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(RuntimeError):
        recogniser.transcribe_verbose(str(audio))


def test_a_refusal_is_not_retried(recogniser, audio, server, monkeypatch):
    monkeypatch.setattr(module.Recogniser, "BACKOFFS", (0.0, 0.0))
    server.fail_times = 99
    server.status = 401
    with pytest.raises(RuntimeError):
        recogniser.transcribe_verbose(str(audio))
    assert server.count("transcribe") == 1


@pytest.mark.parametrize("message, transient", [
    ("service unavailable", True),
    ("gateway timeout", True),
    ("rate limit reached", True),
    ("connection reset", True),
    ("Error code: 401 - invalid key", False),
])
def test_transient_errors_are_told_apart(message, transient):
    assert module.is_transient_error(RuntimeError(message)) is transient
