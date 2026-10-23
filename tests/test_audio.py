"""Voicing per slide, with the retries a busy server needs."""

import pytest

from pptx_screencast import audio as module
from pptx_screencast.config import resolve
from pptx_screencast.errors import ModelError


def _settings(server=None, **kwargs):
    return resolve(
        base_url=(server.base_url if server else "http://127.0.0.1:1/v1"),
        model="chat",
        tts_model="tts",
        voice="alloy",
        **kwargs,
    )


def test_every_slide_with_text_gets_a_file(tmp_path, server):
    paths = module.speak_all(["One sentence.", "", "Three."], tmp_path, _settings(server))
    assert paths[0] is not None and paths[0].exists()
    assert paths[1] is None
    assert paths[2] is not None
    assert server.count("speech") == 2


def test_an_excluded_slide_is_not_spoken(tmp_path, server):
    paths = module.speak_all(
        ["One.", "Two.", "Three."], tmp_path, _settings(server), excluded={1}
    )
    assert paths[1] is None
    assert server.count("speech") == 2


def test_the_files_are_named_in_slide_order(tmp_path, server):
    paths = module.speak_all(["One.", "Two."], tmp_path, _settings(server))
    assert paths[0].name == "slide_000.mp3"
    assert paths[1].name == "slide_001.mp3"


def test_progress_reports_every_slide(tmp_path, server):
    seen = []
    module.speak_all(
        ["One.", "", "Three."], tmp_path, _settings(server),
        on_slide_done=lambda done, total, index: seen.append((done, total, index)),
        max_workers=1,
    )
    assert [s[2] for s in seen] == [0, 1, 2]
    assert seen[-1][0] == 3
    assert all(s[1] == 3 for s in seen)


def test_the_speed_never_goes_to_the_server(tmp_path, server):
    module.speak_all(["One."], tmp_path, _settings(server, speed=0.8))
    sent = [r for r in server.requests if r["route"] == "speech"][0]["body"]
    assert "speed" not in sent


def test_the_voice_and_the_model_go_to_the_server(tmp_path, server):
    module.speak_all(["One."], tmp_path, _settings(server))
    sent = [r for r in server.requests if r["route"] == "speech"][0]["body"]
    assert sent["voice"] == "alloy"
    assert sent["model"] == "tts"


def test_a_busy_server_gets_another_try(tmp_path, server, monkeypatch):
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.fail_times = 2
    server.status = 503
    paths = module.speak_all(["One sentence."], tmp_path, _settings(server))
    assert paths[0] is not None
    assert server.count("speech") == 3


def test_a_server_that_stays_down_ends_in_an_error(tmp_path, server, monkeypatch):
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0,))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        module.speak_all(["One sentence."], tmp_path, _settings(server), max_workers=1)


def test_a_dead_server_is_asked_exactly_once_per_attempt(tmp_path, server, monkeypatch):
    """The retries of this package must not multiply with the ones of the voice."""
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        module.speak_all(["One sentence."], tmp_path, _settings(server), max_workers=1)
    assert server.count("speech") == len(module.RETRY_DELAYS) + 1 == 4


def test_the_voice_makes_no_attempt_of_its_own():
    assert module.TTS_MAX_RETRIES == 0


def test_a_refused_request_is_not_retried(tmp_path, server, monkeypatch):
    waits = []
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0))
    server.fail_times = 99
    server.status = 401
    with pytest.raises(ModelError):
        module.speak_all(["One sentence."], tmp_path, _settings(server), max_workers=1)
    assert server.count("speech") == 1
    assert waits == []


@pytest.mark.parametrize("message, transient", [
    ("Request failed (503)", True),
    ("Request failed (429)", True),
    ("Request to http://x/v1 failed: Error code: 503 - {'message': 'busy'}", True),
    ("Error code: 500", True),
    ("Request failed (401)", False),
    ("Request to http://x/v1 failed: Error code: 401 - invalid key", False),
    ("Request failed, nothing came back", False),
])
def test_a_transient_error_is_told_apart_from_a_refusal(message, transient):
    """Both wordings count, the voice and the source client phrase it differently."""
    assert module.is_transient(RuntimeError(message)) is transient
