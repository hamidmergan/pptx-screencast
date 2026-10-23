"""Reading the word times back out of the finished audio."""

import pytest

from pptx_screencast import stt as module
from pptx_screencast.client import make_stt_client
from pptx_screencast.config import resolve
from pptx_screencast.errors import ModelError, ScreencastError


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
    with pytest.raises(ModelError):
        recogniser.transcribe_verbose(str(audio))


def test_the_failure_stays_inside_the_error_contract(recogniser, audio, server, monkeypatch):
    """A RuntimeError would walk past every caller that catches ScreencastError."""
    monkeypatch.setattr(module.Recogniser, "BACKOFFS", ())
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ScreencastError):
        recogniser.transcribe_verbose(str(audio))


def test_a_refusal_is_not_retried(recogniser, audio, server, monkeypatch):
    monkeypatch.setattr(module.Recogniser, "BACKOFFS", (0.0, 0.0))
    server.fail_times = 99
    server.status = 401
    with pytest.raises(ModelError):
        recogniser.transcribe_verbose(str(audio))
    assert server.count("transcribe") == 1


# -- The time the whole subtitle step gets --

def test_a_wait_that_runs_past_the_deadline_is_not_taken(audio, server, monkeypatch):
    """Eight attempts are up to 1580 seconds, which nothing used to bound."""
    import time

    waits = []
    monkeypatch.setattr(module.time, "sleep", lambda s: waits.append(s))
    settings = resolve(
        base_url=server.base_url, model="chat", stt_model="whisper", require_voice=False
    )
    recogniser = module.Recogniser(
        make_stt_client(settings), "whisper", deadline=time.monotonic() + 20
    )
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        recogniser.transcribe_verbose(str(audio))
    # Only the waits of 5 and 15 fit into 20 seconds, the 60 does not.
    assert waits == [5, 15]
    assert server.count("transcribe") == 3


def test_without_a_deadline_the_whole_ladder_is_walked(audio, server, monkeypatch):
    waits = []
    monkeypatch.setattr(module.time, "sleep", lambda s: waits.append(s))
    settings = resolve(
        base_url=server.base_url, model="chat", stt_model="whisper", require_voice=False
    )
    recogniser = module.Recogniser(make_stt_client(settings), "whisper")
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        recogniser.transcribe_verbose(str(audio))
    assert waits == list(module.Recogniser.BACKOFFS)


def test_a_recogniser_says_when_its_time_is_up():
    import time

    assert module.Recogniser(None, "whisper").out_of_time() is False
    assert module.Recogniser(None, "whisper", deadline=time.monotonic() - 1).out_of_time()
    assert not module.Recogniser(None, "whisper", deadline=time.monotonic() + 60).out_of_time()


class _Answer:
    def __init__(self, status):
        self.status_code = status


class _Refused(Exception):
    def __init__(self, status):
        super().__init__("the server said no")
        self.status_code = status


@pytest.mark.parametrize("status, transient", [
    (408, True),
    (429, True),
    (500, True),
    (502, True),
    (503, True),
    (504, True),
    (400, False),
    (401, False),
    (403, False),
    (404, False),
    (200, False),
])
def test_transient_errors_are_told_apart_by_their_status(status, transient):
    assert module.is_transient_error(_Refused(status)) is transient


def test_the_status_is_also_read_off_the_answer():
    error = RuntimeError("something")
    error.response = _Answer(503)
    assert module.is_transient_error(error) is True


def test_the_status_is_also_read_off_the_cause():
    try:
        try:
            raise _Refused(429)
        except _Refused as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert module.is_transient_error(outer) is True


@pytest.mark.parametrize("message", [
    "service unavailable",
    "gateway timeout",
    "rate limit reached",
    "connection reset",
    "model does not support connection pooling",
])
def test_no_message_text_decides_about_a_retry(message):
    """A 400 that mentions a timeout must not start a ladder of waits."""
    assert module.is_transient_error(RuntimeError(message)) is False


def test_a_refused_connection_is_transient():
    import httpx
    from openai import APIConnectionError

    error = APIConnectionError(request=httpx.Request("POST", "http://127.0.0.1:1/v1"))
    assert module.is_transient_error(error) is True


def test_a_timeout_is_transient():
    import httpx
    from openai import APITimeoutError

    error = APITimeoutError(request=httpx.Request("POST", "http://127.0.0.1:1/v1"))
    assert module.is_transient_error(error) is True
