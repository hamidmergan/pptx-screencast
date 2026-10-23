"""The clients are built from the settings, whichever HTTP library is there."""

import builtins

from pptx_screencast import client as module
from pptx_screencast.config import resolve


def _settings(**kwargs):
    return resolve(base_url="http://127.0.0.1:1/v1", model="chat", require_voice=False, **kwargs)


def test_the_chat_client_takes_the_chat_route():
    made = module.make_chat_client(_settings())
    assert str(made.base_url).startswith("http://127.0.0.1:1/v1")


def test_the_recognition_client_takes_its_own_route():
    settings = _settings(stt_base_url="http://127.0.0.1:2/v1", stt_model="whisper")
    made = module.make_stt_client(settings)
    assert str(made.base_url).startswith("http://127.0.0.1:2/v1")


def test_a_missing_key_becomes_the_placeholder():
    assert _settings().api_key == "none"


def test_the_timeout_falls_back_when_no_http_library_is_there(monkeypatch):
    """The openai package ships httpx in some versions and httpx2 in others."""
    real_import = builtins.__import__

    def _no_http(name, *args, **kwargs):
        if name in ("httpx", "httpx2"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_http)
    assert module._timeout() == module.READ_TIMEOUT


def test_the_timeout_uses_the_phases_when_a_library_is_there():
    timeout = module._timeout()
    assert timeout != module.READ_TIMEOUT
    assert timeout.read == module.READ_TIMEOUT
    assert timeout.connect == module.CONNECT_TIMEOUT


def test_the_clients_make_no_attempt_of_their_own():
    """The retry policy belongs to this package, with the waits it chose."""
    assert module.CLIENT_MAX_RETRIES == 0
    assert module.make_chat_client(_settings()).max_retries == 0
    settings = _settings(stt_base_url="http://127.0.0.1:2/v1", stt_model="whisper")
    assert module.make_stt_client(settings).max_retries == 0


def test_the_recogniser_is_asked_once_per_attempt(server, tmp_path, monkeypatch):
    from pptx_screencast import stt
    from pptx_screencast.errors import ModelError

    monkeypatch.setattr(stt.Recogniser, "BACKOFFS", (0.0, 0.0))
    audio = tmp_path / "slide.mp3"
    audio.write_bytes(b"not really audio")
    settings = resolve(
        base_url=server.base_url, model="chat", stt_model="whisper", require_voice=False
    )
    server.fail_times = 99
    server.status = 503
    recogniser = stt.Recogniser(module.make_stt_client(settings), "whisper")
    try:
        recogniser.transcribe_verbose(str(audio))
    except ModelError:
        pass
    assert server.count("transcribe") == 3
