"""Shared fixtures: a tiny deck on disk and the fake model server."""

import json
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path(__file__).parent / "data"

# Seconds of speech the fake server pretends per character.
SECONDS_PER_CHAR = 0.02


@pytest.fixture
def sample_deck() -> Path:
    """The small deck that ships with the tests, four slides with notes."""
    return DATA / "sample.pptx"


def _silence(seconds: float) -> bytes:
    """A real MP3 of that length, so ffmpeg and ffprobe see sound."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return b""
    done = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=mono:d={max(seconds, 0.1):.3f}",
            "-c:a", "libmp3lame", "-q:a", "9", "-f", "mp3", "pipe:1",
        ],
        capture_output=True,
    )
    return done.stdout


class FakeServer:
    """Chat, speech and speech recognition, all on one port.

    The chat route answers a script request with one short script per block,
    so the count always matches. `scripts` replaces that answer, `reply`
    replaces every chat answer, and `fail_times` makes the first calls fail.
    """

    def __init__(self):
        self.requests = []
        self.scripts = None
        self.reply = None
        self.fail_times = 0
        self.status = 500
        self.transcript_words = None
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, data: bytes, content_type: str, status: int = 200):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _json(self, payload, status: int = 200):
                self._send(json.dumps(payload).encode(), "application/json", status)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                if self.path.endswith("/chat/completions"):
                    return outer.chat(self, json.loads(raw))
                if self.path.endswith("/audio/speech"):
                    return outer.speech(self, json.loads(raw))
                if self.path.endswith("/audio/transcriptions"):
                    return outer.transcribe(self, raw)
                self._json({"error": "unknown route"}, 404)

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    # -- routes --

    def chat(self, handler, body):
        self.requests.append({"route": "chat", "body": body})
        if self.fail_times > 0:
            self.fail_times -= 1
            return handler._json({"error": {"message": "busy"}}, self.status)
        content = self.answer(body)
        handler._json(
            {
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": body.get("model", "chat"),
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
            }
        )

    def answer(self, body) -> str:
        if self.reply is not None:
            return self.reply
        if self.scripts is not None:
            return "\n|||\n".join(self.scripts)
        system = body["messages"][0]["content"]
        user = body["messages"][1]["content"]
        if "You translate" in system:
            return f"[translated] {user}"
        blocks = user.split("\n===\n")
        return "\n|||\n".join(
            f"Slide {i + 1} says something about it." for i in range(len(blocks))
        )

    def speech(self, handler, body):
        self.requests.append({"route": "speech", "body": body})
        if self.fail_times > 0:
            self.fail_times -= 1
            return handler._json({"error": {"message": "busy"}}, self.status)
        seconds = max(0.2, len(body.get("input", "")) * SECONDS_PER_CHAR)
        handler._send(_silence(seconds), "audio/mpeg")

    def transcribe(self, handler, raw: bytes):
        self.requests.append({"route": "transcribe", "size": len(raw)})
        if self.fail_times > 0:
            self.fail_times -= 1
            return handler._json({"error": {"message": "busy"}}, self.status)
        words = self.transcript_words or ["Hello", "there", "again"]
        step = 0.5
        handler._json(
            {
                "text": " ".join(words),
                "segments": [
                    {
                        "id": i,
                        "start": round(i * step, 3),
                        "end": round((i + 1) * step, 3),
                        "text": " " + word,
                    }
                    for i, word in enumerate(words)
                ],
            }
        )

    # -- helpers --

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_port}/v1"

    def count(self, route: str) -> int:
        return sum(1 for r in self.requests if r["route"] == route)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    fake = FakeServer()
    yield fake
    fake.stop()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No setting of the machine may reach into a test."""
    import os

    for name in list(os.environ):
        if (
            name.startswith("PPTX_SCREENCAST_")
            or name.startswith("DOC2SPEECH_")
            or name == "OPENAI_API_KEY"
        ):
            monkeypatch.delenv(name)
