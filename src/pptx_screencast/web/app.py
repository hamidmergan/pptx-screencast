"""Web API for the screencast page.

One deck at a time, in two steps. First the narration is written, so it can
be read and corrected on the page. Then the video is built from the scripts
the person accepted. Nothing is stored on disk after the run, the finished
video lives in memory until the next deck replaces it.
"""

import io
import logging
import os
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import config
from ..core import build_scripts, make_video
from ..errors import ConfigError, ScreencastError
from ..info import build_info
from ..paths import safe_stem
from ..script_file import parse_script_file, render_script_file
from ..selection import parse_slides
from ..slides import extract_text_per_slide
from ..tools import missing_tools
from ..video import get_video_duration

logger = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
MB = 1024 * 1024

# Largest deck the page accepts.
MAX_UPLOAD_MB = 100

# How the narration is written.
SOURCES = ("generate", "notes", "import")


class Job:
    """The one deck the page is working on, and what came out of it."""

    def __init__(self) -> None:
        self.state = "idle"       # idle, running, done or error
        self.step = ""            # scripts, speak, video, subtitles or join
        self.done = 0
        self.total = 0
        self.error = ""
        self.name = "screencast"
        self.deck = b""
        self.scripts: list = []
        self.slides = 0
        self.video = b""
        self.vtt = ""
        self.srt = ""
        self.settings: dict = {}
        self.duration = 0.0

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "step": self.step,
            "done": self.done,
            "total": self.total,
            "error": self.error,
            "scripts": self.scripts,
            "slides": self.slides,
            "name": self.name,
            "has_video": bool(self.video),
            "has_subtitles": bool(self.vtt),
        }


def _work_file(name: str, suffix: str = ".pptx") -> Path:
    """A file of its own for one run, removed again when the run is over."""
    handle, path = tempfile.mkstemp(prefix=f"{name}-", suffix=suffix)
    os.close(handle)
    return Path(path)


def _hostname(host: str) -> str:
    if host.startswith("["):
        return host[1:host.find("]")].lower()
    return host.rsplit(":", 1)[0].lower() if host.count(":") == 1 else host.lower()


def create_app(
    defaults: Optional[dict] = None,
    allowed_hosts: Optional[Sequence[str]] = None,
    client=None,
    stt_client=None,
) -> FastAPI:
    """The screencast page and its JSON API.

    `defaults` are the settings the page starts with. Everything can also be
    typed into the fields of the page. `allowed_hosts` limits the Host header
    (against DNS rebinding), requests from another origin are refused.
    """
    defaults = {k: v for k, v in (defaults or {}).items() if v not in (None, "")}
    job = Job()
    lock = threading.Lock()

    app = FastAPI(title="pptx-screencast")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    hosts = {h.lower() for h in allowed_hosts} if allowed_hosts is not None else None

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = request.headers.get("host", "")
        if hosts is not None and _hostname(host) not in hosts:
            return PlainTextResponse("Unknown host", status_code=400)
        origin = request.headers.get("origin")
        # Also behind a reverse proxy.
        own = {host.lower(), request.headers.get("x-forwarded-host", "").lower()}
        if origin is not None and urlsplit(origin).netloc.lower() not in own:
            return PlainTextResponse("Cross-origin requests are not allowed", status_code=403)
        if request.url.path == "/api/scripts":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_UPLOAD_MB * MB + MB:
                return PlainTextResponse(
                    f"The upload is larger than {MAX_UPLOAD_MB} MB.", status_code=413)
        return await call_next(request)

    def options(form: dict) -> dict:
        """The settings of one request: the page first, then the defaults."""
        chosen = {k: (v.strip() or None) for k, v in form.items() if isinstance(v, str)}
        chosen.update({k: v for k, v in form.items() if not isinstance(v, str)})
        for key, value in defaults.items():
            if chosen.get(key) is None:
                chosen[key] = value
        return {k: v for k, v in chosen.items() if v is not None}

    def _switch(raw: str) -> Optional[bool]:
        """A checkbox of the page: on, off, or nothing said at all.

        An unticked box has to send `off`, otherwise a default from the
        environment would switch the option back on behind the user's back.
        """
        value = raw.strip().lower()
        if value in ("on", "true", "1", "yes"):
            return True
        if value in ("off", "false", "0", "no"):
            return False
        return None

    def _number(raw: str, label: str) -> Optional[float]:
        if not raw.strip():
            return None
        try:
            return float(raw)
        except ValueError:
            raise HTTPException(400, f"{label} must be a number, for example 1.0.")

    def _claim(step: str, total: int = 0) -> None:
        with lock:
            if job.state == "running":
                raise HTTPException(409, "A screencast is already being created.")
            job.state, job.step, job.done, job.total, job.error = "running", step, 0, total, ""

    def _failed(exc: Exception) -> None:
        with lock:
            job.state = "error"
            job.error = str(exc) or exc.__class__.__name__

    def _report(step: str, done: int, total: int) -> None:
        with lock:
            job.step, job.done, job.total = step, done, total

    # -- Step one: the narration --

    def run_scripts(deck: Path, chosen: dict, source: str, translate: str) -> None:
        try:
            settings = config.resolve(require_voice=False, **chosen)
            scripts = build_scripts(
                deck, settings,
                notes=(source == "notes"),
                translate=translate,
                client=client,
                progress=_report,
            )
        except Exception as exc:
            _failed(exc)
            return
        finally:
            deck.unlink(missing_ok=True)
        with lock:
            job.state, job.scripts, job.error = "done", scripts, ""

    @app.post("/api/scripts")
    async def start_scripts(
        file: UploadFile = File(...),
        source: str = Form("generate"),
        language: str = Form(""),
        translate: str = Form(""),
        base_url: str = Form(""),
        model: str = Form(""),
        api_key: str = Form(""),
        script_file: Optional[UploadFile] = File(None),
    ):
        if source not in SOURCES:
            raise HTTPException(400, "Unknown way of creating the scripts.")
        if not (file.filename or "").lower().endswith(".pptx"):
            raise HTTPException(400, "Only .pptx file")
        data = await file.read()
        if len(data) > MAX_UPLOAD_MB * MB:
            raise HTTPException(413, f"The file is larger than {MAX_UPLOAD_MB} MB.")
        try:
            slide_texts = extract_text_per_slide(data)
        except Exception:
            raise HTTPException(400, "The presentation could not be read.")
        if not slide_texts:
            raise HTTPException(400, "The presentation holds no visible slide.")

        with lock:
            job.deck, job.name, job.slides = data, safe_stem(file.filename), len(slide_texts)
            job.video, job.vtt, job.srt, job.scripts = b"", "", "", []

        if source == "import":
            if script_file is None or not script_file.filename:
                raise HTTPException(400, "Please select a script file first.")
            raw = (await script_file.read()).decode("utf-8", "replace")
            try:
                scripts = parse_script_file(raw)
            except ScreencastError as exc:
                raise HTTPException(400, str(exc))
            if len(scripts) != len(slide_texts):
                raise HTTPException(
                    400,
                    f"The script file has {len(scripts)} slide(s), the deck has "
                    f"{len(slide_texts)}. The slide count must match.",
                )
            with lock:
                job.state, job.scripts, job.error = "done", scripts, ""
            return {"state": "done"}

        chosen = options({"base_url": base_url, "model": model, "api_key": api_key,
                          "language": language})
        _claim("scripts", len(slide_texts))
        deck_path = _work_file(job.name)
        deck_path.write_bytes(data)
        threading.Thread(
            target=run_scripts, args=(deck_path, chosen, source, translate.strip()), daemon=True
        ).start()
        return {"state": "running"}

    # -- Step two: the video --

    def run_video(deck: Path, scripts: list, chosen: dict, slides: Optional[list]) -> None:
        output = deck.with_suffix(".mp4")
        try:
            script_path = deck.with_suffix(".md")
            script_path.write_text(render_script_file(scripts, job.name), encoding="utf-8")
            make_video(
                deck, output,
                script=script_path,
                slides=slides,
                client=client,
                stt_client=stt_client,
                progress=_report,
                **chosen,
            )
            video = output.read_bytes()
            vtt = output.with_suffix(".vtt")
            srt = output.with_suffix(".srt")
            with lock:
                job.video = video
                job.vtt = vtt.read_text(encoding="utf-8") if vtt.exists() else ""
                job.srt = srt.read_text(encoding="utf-8") if srt.exists() else ""
                job.duration = get_video_duration(output)
                job.state, job.error = "done", ""
        except Exception as exc:
            _failed(exc)
        finally:
            for path in (deck, output, deck.with_suffix(".md"),
                         output.with_suffix(".vtt"), output.with_suffix(".srt")):
                path.unlink(missing_ok=True)

    @app.post("/api/render")
    def start_render(
        scripts: List[str] = Form([]),
        voice: str = Form(""),
        speed: str = Form(""),
        language: str = Form(""),
        slide_pause: str = Form(""),
        resolution: str = Form(""),
        subtitles: str = Form(""),
        burn_in: str = Form(""),
        slides: str = Form(""),
        base_url: str = Form(""),
        model: str = Form(""),
        api_key: str = Form(""),
        tts_base_url: str = Form(""),
        tts_model: str = Form(""),
        tts_api_key: str = Form(""),
        stt_base_url: str = Form(""),
        stt_model: str = Form(""),
        stt_api_key: str = Form(""),
    ):
        with lock:
            deck_bytes, name, count = job.deck, job.name, job.slides
        if not deck_bytes:
            raise HTTPException(400, "Please upload a presentation first.")
        if len(scripts) != count:
            raise HTTPException(400, f"Every one of the {count} slides needs a narration.")

        chosen = options({
            "base_url": base_url, "model": model, "api_key": api_key,
            "tts_base_url": tts_base_url, "tts_model": tts_model, "tts_api_key": tts_api_key,
            "stt_base_url": stt_base_url, "stt_model": stt_model, "stt_api_key": stt_api_key,
            "voice": voice, "language": language,
            "subtitles": _switch(subtitles),
            "burn_in": _switch(burn_in),
        })
        for key, raw, label in (("speed", speed, "Speed"),
                                ("slide_pause", slide_pause, "The pause"),
                                ("resolution", resolution, "The image quality")):
            value = _number(raw, label)
            if value is not None:
                chosen[key] = int(value) if key == "resolution" else value
        try:
            chosen_slides = parse_slides(slides) if slides.strip() else None
            resolved = config.resolve(**chosen)
        except ConfigError as exc:
            raise HTTPException(400, str(exc))
        if missing := missing_tools():
            raise HTTPException(500, "Missing programs on the server: " + ", ".join(missing))

        _claim("speak", count)
        with lock:
            job.scripts = list(scripts)
            # The resolved values, so the info file names the defaults too.
            job.settings = {
                "language": resolved.language,
                "voice": resolved.voice,
                "speed": resolved.speed,
                "slide_pause": resolved.slide_pause,
            }
            job.video, job.vtt, job.srt = b"", "", ""
        deck_path = _work_file(name)
        deck_path.write_bytes(deck_bytes)
        threading.Thread(
            target=run_video, args=(deck_path, list(scripts), chosen, chosen_slides), daemon=True
        ).start()
        return {"state": "running"}

    # -- What the page reads --

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/info")
    def info():
        """What the page fills into its fields, and what it tells the user."""
        return {
            "base_url": defaults.get("base_url", ""),
            "model": defaults.get("model", ""),
            "tts_base_url": defaults.get("tts_base_url", ""),
            "tts_model": defaults.get("tts_model", ""),
            "stt_base_url": defaults.get("stt_base_url", ""),
            "stt_model": defaults.get("stt_model", ""),
            "voice": defaults.get("voice", ""),
            "language": defaults.get("language", config.LANGUAGE),
            "speed": defaults.get("speed", config.SPEED),
            "slide_pause": defaults.get("slide_pause", config.SLIDE_PAUSE),
            "resolution": defaults.get("resolution", config.RESOLUTION),
            "subtitles": bool(defaults.get("subtitles", False)),
            "burn_in": bool(defaults.get("burn_in", False)),
            "has_key": bool(defaults.get("api_key")),
            "max_upload_mb": MAX_UPLOAD_MB,
            "max_slides": config.MAX_SLIDES,
            "missing_tools": missing_tools(),
        }

    @app.get("/api/job")
    def state():
        with lock:
            return job.as_dict()

    @app.get("/api/scripts")
    def scripts_of_the_job():
        with lock:
            if not job.scripts:
                raise HTTPException(404, "There are no scripts yet.")
            return {"scripts": job.scripts, "slides": job.slides}

    @app.get("/api/video")
    def video():
        with lock:
            if not job.video:
                raise HTTPException(404, "There is no video yet.")
            data, name = job.video, job.name
        return Response(
            content=data,
            media_type="video/mp4",
            headers={"Content-Disposition": f'attachment; filename="{name}.mp4"'},
        )

    @app.get("/api/subtitles.vtt")
    def subtitles_vtt():
        with lock:
            if not job.vtt:
                raise HTTPException(404, "There are no subtitles.")
            return Response(content=job.vtt, media_type="text/vtt")

    @app.get("/api/subtitles.srt")
    def subtitles_srt():
        with lock:
            if not job.srt:
                raise HTTPException(404, "There are no subtitles.")
            return Response(
                content=job.srt,
                media_type="application/x-subrip",
                headers={"Content-Disposition": f'attachment; filename="{job.name}.srt"'},
            )

    @app.get("/api/zip")
    def everything():
        """The video, the subtitles, the narration and an info file in one ZIP."""
        with lock:
            if not job.video:
                raise HTTPException(404, "There is no video yet.")
            name, data, vtt, srt = job.name, job.video, job.vtt, job.srt
            scripts, settings, duration = list(job.scripts), dict(job.settings), job.duration
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{name}.mp4", data)
            if vtt:
                archive.writestr(f"{name}.vtt", vtt)
            if srt:
                archive.writestr(f"{name}.srt", srt)
            archive.writestr(f"{name}.md", render_script_file(scripts, name))
            archive.writestr("info.txt", build_info(
                name,
                slides=len(scripts),
                characters=sum(len(s) for s in scripts),
                language=str(settings.get("language", "")),
                voice=str(settings.get("voice", "")),
                speed=settings.get("speed"),
                slide_pause=settings.get("slide_pause"),
                subtitles=bool(vtt),
                duration=duration or None,
            ))
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
        )

    return app
