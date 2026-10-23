"""The chat client against a real HTTP server, not a stand-in object."""

import pytest

from pptx_screencast.config import resolve
from pptx_screencast.llm import make_llm


@pytest.fixture
def llm(server):
    settings = resolve(base_url=server.base_url, model="chat", require_voice=False)
    return make_llm(settings)


def test_one_script_per_slide_comes_back_over_http(llm, server):
    scripts = llm.generate_scripts_batch(
        ["First slide text", "Second slide text"], add_greeting=False, add_closing=False
    )
    assert len(scripts) == 2
    assert server.count("chat") == 1


def test_the_batch_size_from_the_settings_is_used(server):
    settings = resolve(base_url=server.base_url, model="chat", batch_size=2, require_voice=False)
    make_llm(settings).generate_scripts_batch(
        [f"Slide {i}" for i in range(5)], add_greeting=False, add_closing=False
    )
    assert server.count("chat") == 3, "five slides in batches of two"


def test_the_model_name_goes_out_with_every_request(llm, server):
    llm.generate_scripts_batch(["One slide"], add_greeting=False, add_closing=False)
    assert server.requests[0]["body"]["model"] == "chat"


def test_a_translation_uses_the_same_client(llm, server):
    assert llm.translate_text("Hello.", "German") == "[translated] Hello."
    assert server.count("chat") == 1


def test_a_refused_key_is_not_retried_forever(server, monkeypatch):
    from pptx_screencast import scripts as module

    monkeypatch.setattr(module, "_BATCH_RETRY_DELAY", 0.0)
    server.fail_times = 99
    server.status = 401
    settings = resolve(base_url=server.base_url, model="chat", require_voice=False)
    with pytest.raises(RuntimeError):
        make_llm(settings).generate_scripts_batch(
            ["One slide"], add_greeting=False, add_closing=False
        )
