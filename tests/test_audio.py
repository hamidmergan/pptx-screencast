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


@pytest.mark.parametrize("status, transient", [
    (None, True),   # no answer arrived at all, a timeout or a refused connection
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
])
def test_the_voice_decides_what_is_worth_another_try(status, transient):
    """The verdict comes from the error itself, no message text is read."""
    from doc2speech import ModelError as VoiceError

    assert module.is_transient(VoiceError("nope", status)) is transient


def test_a_failure_that_is_not_the_servers_is_final():
    """A missing setting or an empty text does not change on another try."""
    from doc2speech import ConfigError, EmptyTextError

    assert not module.is_transient(ConfigError("Missing: voice"))
    assert not module.is_transient(EmptyTextError("Please enter some text."))
    assert not module.is_transient(RuntimeError("something else entirely"))


# -- A narration long enough to need several requests --

# 1980 characters, just under the default ceiling of 2000.
LONG_SCRIPT = (
    "The slide shows the measured result of the second experiment. "
    * 40
)[:1980]


def test_a_long_narration_is_split_into_parts():
    parts = module.split_narration(LONG_SCRIPT)
    assert len(parts) == 6, "1980 characters, at most 400 per request"
    assert all(len(part) <= module.CHUNK_CHARS for part in parts)
    assert "".join(parts) == LONG_SCRIPT


def test_a_healthy_server_is_asked_once_per_part(tmp_path, server):
    paths = module.speak_all([LONG_SCRIPT], tmp_path, _settings(server), max_workers=1)
    assert paths[0] is not None and paths[0].stat().st_size > 0
    assert server.count("speech") == 6


def test_one_bad_part_costs_one_more_request_and_not_the_whole_slide(
    tmp_path, server, monkeypatch
):
    """The retry sits on the part, so the four good parts are not paid twice."""
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.speech_fail_indexes = {2}
    server.status = 503
    paths = module.speak_all([LONG_SCRIPT], tmp_path, _settings(server), max_workers=1)
    assert paths[0] is not None
    assert server.count("speech") == 7


def test_a_dead_server_stops_after_the_first_part_gave_up(tmp_path, server, monkeypatch):
    """Four attempts on one part, then the slide is over. No other part is asked."""
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        module.speak_all([LONG_SCRIPT], tmp_path, _settings(server), max_workers=1)
    assert server.count("speech") == 4


def test_the_parts_of_all_slides_share_one_pool(tmp_path, server):
    """Two long slides are 12 requests, never more than max_workers at a time."""
    import threading

    open_now = [0]
    seen = [0]
    lock = threading.Lock()
    real = server.speech

    def counting(handler, body):
        with lock:
            open_now[0] += 1
            seen[0] = max(seen[0], open_now[0])
        try:
            return real(handler, body)
        finally:
            with lock:
                open_now[0] -= 1

    server.speech = counting
    paths = module.speak_all(
        [LONG_SCRIPT, LONG_SCRIPT], tmp_path, _settings(server), max_workers=2
    )
    assert all(p is not None for p in paths)
    assert server.count("speech") == 12
    assert seen[0] <= 2


def test_the_progress_counts_only_the_slides_it_speaks(tmp_path, server):
    seen = []
    module.speak_all(
        ["One.", "Two.", "Three.", "Four."], tmp_path, _settings(server),
        excluded={1, 3},
        on_slide_done=lambda done, total, index: seen.append((done, total, index)),
        max_workers=1,
    )
    assert seen == [(1, 2, 0), (2, 2, 2)]


def test_a_foreign_speed_variable_is_pointed_out(tmp_path, server, monkeypatch, caplog):
    monkeypatch.setenv("DOC2SPEECH_SPEED", "0.8")
    with caplog.at_level("WARNING"):
        module.speak_all(["One."], tmp_path, _settings(server))
    assert "DOC2SPEECH_SPEED" in caplog.text


def test_a_whole_deck_against_a_dead_server_costs_one_ladder(tmp_path, server, monkeypatch):
    """The run stops asking as soon as one part has given up for good.

    40 slides of 6 parts each used to be 960 requests against a server that
    is down. Now only the parts that are in flight walk their ladder, so the
    cost is bounded by the number of workers and not by the deck.
    """
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        module.speak_all([LONG_SCRIPT] * 40, tmp_path, _settings(server), max_workers=4)
    attempts = len(module.RETRY_DELAYS) + 1
    assert attempts <= server.count("speech") <= 4 * attempts


def test_one_worker_against_a_dead_deck_pays_exactly_one_ladder(
    tmp_path, server, monkeypatch
):
    monkeypatch.setattr(module, "RETRY_DELAYS", (0.0, 0.0, 0.0))
    server.fail_times = 99
    server.status = 503
    with pytest.raises(ModelError):
        module.speak_all([LONG_SCRIPT] * 40, tmp_path, _settings(server), max_workers=1)
    assert server.count("speech") == 4
