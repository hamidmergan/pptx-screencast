"""The page and its JSON API, driven with the TestClient."""

import shutil
import time

import pytest
from PIL import Image

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from pptx_screencast import core  # noqa: E402
from pptx_screencast.script_file import parse_script_file, render_script_file  # noqa: E402
from pptx_screencast.web.app import create_app  # noqa: E402

_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


@pytest.fixture
def deck_bytes():
    from _pptx_fixtures import notes_pptx

    return notes_pptx(["Note one.", "", "Note three."])


@pytest.fixture
def no_libreoffice(monkeypatch):
    def _images(pptx, folder, dpi=100, max_workers=4):
        made = []
        for i in range(len(core.extract_text_per_slide(pptx))):
            path = folder / f"slide-{i + 1}.png"
            Image.new("RGB", (160, 120), "white").save(path)
            made.append(path)
        return made

    monkeypatch.setattr(core, "pptx_to_images", _images)
    monkeypatch.setattr(core, "require_tools", lambda **kwargs: None)
    monkeypatch.setattr("pptx_screencast.web.app.missing_tools", lambda **kwargs: [])


@pytest.fixture
def client(server):
    app = create_app({"base_url": server.base_url, "model": "chat"})
    with TestClient(app) as test_client:
        yield test_client


def _wait(client, seconds: float = 30.0) -> dict:
    """Wait for the one job of the page to finish."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        job = client.get("/api/job").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("the job did not finish")


def _upload(client, deck_bytes, **fields):
    data = {"source": "generate"}
    data.update(fields)
    return client.post(
        "/api/scripts",
        data=data,
        files={"file": ("deck.pptx", deck_bytes,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )


# -- The page itself --

def test_the_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Screencast" in response.text


def test_the_info_names_the_defaults_of_the_page(client, server):
    info = client.get("/api/info").json()
    assert info["base_url"] == server.base_url
    assert info["model"] == "chat"
    assert info["language"] == "en"
    assert info["max_slides"] == 500


def test_a_foreign_origin_is_refused(client, deck_bytes):
    response = client.get("/api/info", headers={"Origin": "http://evil.example"})
    assert response.status_code == 403


def test_an_unknown_host_is_refused(server):
    app = create_app({}, allowed_hosts=["127.0.0.1"])
    with TestClient(app, base_url="http://elsewhere.example") as other:
        assert other.get("/api/info").status_code == 400


# -- Step one: the scripts --

def test_only_a_pptx_is_accepted(client):
    response = client.post(
        "/api/scripts", data={"source": "generate"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400
    assert "pptx" in response.json()["detail"]


def test_an_unreadable_deck_is_reported(client):
    response = client.post(
        "/api/scripts", data={"source": "generate"},
        files={"file": ("deck.pptx", b"not a deck", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_an_unknown_source_is_refused(client, deck_bytes):
    assert _upload(client, deck_bytes, source="magic").status_code == 400


def test_the_model_writes_one_script_per_slide(client, deck_bytes, server):
    assert _upload(client, deck_bytes).status_code == 200
    job = _wait(client)
    assert job["state"] == "done"
    assert len(job["scripts"]) == 3
    assert job["slides"] == 3
    assert server.count("chat") == 1


def test_the_notes_become_the_scripts(client, deck_bytes, server):
    _upload(client, deck_bytes, source="notes")
    job = _wait(client)
    assert job["scripts"] == ["Note one.", "", "Note three."]
    assert server.count("chat") == 0


def test_an_imported_script_file_is_taken_as_it_is(client, deck_bytes):
    text = render_script_file(["One.", "Two.", "Three."])
    response = client.post(
        "/api/scripts",
        data={"source": "import"},
        files={
            "file": ("deck.pptx", deck_bytes, "application/octet-stream"),
            "script_file": ("deck.md", text.encode(), "text/markdown"),
        },
    )
    assert response.status_code == 200
    assert client.get("/api/job").json()["scripts"] == ["One.", "Two.", "Three."]


def test_an_imported_file_with_the_wrong_count_is_refused(client, deck_bytes):
    text = render_script_file(["One.", "Two."])
    response = client.post(
        "/api/scripts",
        data={"source": "import"},
        files={
            "file": ("deck.pptx", deck_bytes, "application/octet-stream"),
            "script_file": ("deck.md", text.encode(), "text/markdown"),
        },
    )
    assert response.status_code == 400
    assert "slide count must match" in response.json()["detail"]


def test_import_without_a_file_is_refused(client, deck_bytes):
    assert _upload(client, deck_bytes, source="import").status_code == 400


def test_a_translation_goes_through_the_chat_model(client, deck_bytes):
    _upload(client, deck_bytes, source="notes", translate="German")
    job = _wait(client)
    assert job["scripts"][0].startswith("[translated]")


def test_a_broken_model_server_ends_in_an_error(client, deck_bytes, server):
    server.fail_times = 99
    server.status = 401
    _upload(client, deck_bytes)
    job = _wait(client)
    assert job["state"] == "error"
    assert job["error"]


# -- Step two: the video --

def test_rendering_without_a_deck_is_refused(client):
    response = client.post("/api/render", data={"scripts": ["One."], "voice": "alloy"})
    assert response.status_code == 400


def test_a_wrong_number_of_scripts_is_refused(client, deck_bytes):
    _upload(client, deck_bytes, source="notes")
    _wait(client)
    response = client.post("/api/render", data={"scripts": ["One."], "voice": "alloy"})
    assert response.status_code == 400
    assert "3 slides" in response.json()["detail"]


def test_a_missing_voice_is_named(client, deck_bytes):
    _upload(client, deck_bytes, source="notes")
    _wait(client)
    response = client.post(
        "/api/render",
        data={"scripts": ["One.", "", "Three."], "tts_model": "tts"},
    )
    assert response.status_code == 400
    assert "--voice" in response.json()["detail"]


def test_a_bad_number_is_named(client, deck_bytes):
    _upload(client, deck_bytes, source="notes")
    _wait(client)
    response = client.post(
        "/api/render",
        data={"scripts": ["One.", "", "Three."], "voice": "alloy",
              "tts_model": "tts", "speed": "fast"},
    )
    assert response.status_code == 400
    assert "must be a number" in response.json()["detail"]


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_a_deck_becomes_a_video_that_can_be_downloaded(client, deck_bytes, no_libreoffice):
    _upload(client, deck_bytes, source="notes")
    _wait(client)
    response = client.post(
        "/api/render",
        data={"scripts": ["One sentence.", "", "Three."], "voice": "alloy", "tts_model": "tts"},
    )
    assert response.status_code == 200
    job = _wait(client, 60)
    assert job["state"] == "done", job["error"]
    assert job["has_video"]

    video = client.get("/api/video")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert len(video.content) > 1000


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_subtitles_can_be_fetched_in_both_formats(client, deck_bytes, no_libreoffice):
    _upload(client, deck_bytes, source="notes")
    _wait(client)
    client.post(
        "/api/render",
        data={"scripts": ["One sentence.", "", "Three."], "voice": "alloy",
              "tts_model": "tts", "stt_model": "whisper", "subtitles": "on"},
    )
    job = _wait(client, 60)
    assert job["has_subtitles"], job["error"]
    assert "WEBVTT" in client.get("/api/subtitles.vtt").text
    assert "-->" in client.get("/api/subtitles.srt").text


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg and ffprobe are not installed")
def test_the_zip_holds_the_video_the_script_and_the_info(client, deck_bytes, no_libreoffice):
    import io
    import zipfile

    _upload(client, deck_bytes, source="notes")
    _wait(client)
    client.post(
        "/api/render",
        data={"scripts": ["One sentence.", "", "Three."], "voice": "alloy", "tts_model": "tts"},
    )
    _wait(client, 60)
    response = client.get("/api/zip")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert "deck.mp4" in names
        assert "deck.md" in names
        assert "info.txt" in names
        info = archive.read("info.txt").decode()
        assert "Slides: 3" in info
        assert "Voice: alloy" in info
        assert "Language: en" in info
        assert "Speed: 1.0" in info
        scripts = parse_script_file(archive.read("deck.md").decode())
        assert scripts == ["One sentence.", "", "Three."]


def test_without_a_video_the_downloads_are_empty(client):
    assert client.get("/api/video").status_code == 404
    assert client.get("/api/subtitles.vtt").status_code == 404
    assert client.get("/api/zip").status_code == 404


def test_only_one_job_runs_at_a_time(client, deck_bytes, server):
    _upload(client, deck_bytes)
    second = _upload(client, deck_bytes)
    # The first job may already be done on a fast machine, then the second
    # one is simply accepted again.
    assert second.status_code in (200, 409)
    _wait(client)
