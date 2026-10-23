"""Default values and resolution of settings.

Order: argument, then environment variable, then default.

Three model routes are configured separately, each with its own base URL,
model and key, and each falling back to the chat values when it has none of
its own:

* chat, for the narration scripts and the translation
* text-to-speech, for the voice
* speech-to-text, for the subtitle times
"""

import os
from dataclasses import dataclass
from typing import Optional

from .errors import ConfigError

ENV_PREFIX = "PPTX_SCREENCAST_"

# Placeholder, because the OpenAI library requires a value.
# Local servers ignore it.
PLACEHOLDER_API_KEY = "none"

# Slides per request to the chat model. More slides in one call keep the
# narration coherent, too many make the answer run into the token ceiling.
BATCH_SIZE = 10

# Chat requests at the same time.
BATCH_MAX_WORKERS = 3

# Seconds per chat request. A batch of slides takes a while.
BATCH_TIMEOUT = 600.0

# Characters per narration. The maximum is a ceiling, not a target.
MIN_CHARS = 1500
MAX_CHARS = 2000

# Most slides a deck may have.
MAX_SLIDES = 500

# Resolution of the rendered slide images in dots per inch.
RESOLUTION = 100

# Frames per second of the still image. At 1 a slide shorter than a second
# would get no frame at all.
FPS = 5

# Seconds of silence after every slide.
SLIDE_PAUSE = 1.0

# Speaking speed. The speed is applied locally with ffmpeg, because many
# servers lower the pitch of the voice when they slow it down.
SPEED = 1.0

# Quality of the video, lower is better and bigger.
CRF = 23

# Slides rendered, voiced or cut at the same time.
MAX_WORKERS = 4

LANGUAGE = "en"


@dataclass(frozen=True)
class Settings:
    base_url: str
    model: str
    api_key: str
    tts_base_url: str
    tts_model: str
    tts_api_key: str
    stt_base_url: str
    stt_model: str
    stt_api_key: str
    voice: str
    speed: float
    language: str
    subtitles: bool
    burn_in: bool
    resolution: int
    fps: int
    slide_pause: float
    crf: int
    min_chars: int
    max_chars: int
    batch_size: int
    batch_max_workers: int
    batch_timeout: float
    max_slides: int
    max_workers: int
    work_dir: Optional[str]

    @property
    def has_stt(self) -> bool:
        """True when a speech recognition model is configured."""
        return bool(self.stt_model and self.stt_base_url)


def _env(name: str) -> Optional[str]:
    value = os.environ.get(ENV_PREFIX + name)
    if value is None or value.strip() == "":
        return None
    return value.strip()


def _flag(raw: str) -> bool:
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _pick(arg, env_name: str, default, cast):
    if arg is not None:
        return arg
    raw = _env(env_name)
    if raw is None:
        return default
    try:
        return cast(raw)
    except ValueError:
        raise ConfigError(
            f"Environment variable {ENV_PREFIX}{env_name} has an invalid value: {raw!r}"
        )


def resolve(
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    tts_base_url: Optional[str] = None,
    tts_model: Optional[str] = None,
    tts_api_key: Optional[str] = None,
    stt_base_url: Optional[str] = None,
    stt_model: Optional[str] = None,
    stt_api_key: Optional[str] = None,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
    language: Optional[str] = None,
    subtitles: Optional[bool] = None,
    burn_in: Optional[bool] = None,
    resolution: Optional[int] = None,
    fps: Optional[int] = None,
    slide_pause: Optional[float] = None,
    crf: Optional[int] = None,
    min_chars: Optional[int] = None,
    max_chars: Optional[int] = None,
    batch_size: Optional[int] = None,
    batch_max_workers: Optional[int] = None,
    batch_timeout: Optional[float] = None,
    max_slides: Optional[int] = None,
    max_workers: Optional[int] = None,
    work_dir: Optional[str] = None,
    require_voice: bool = True,
) -> Settings:
    """Build the settings, or raise ConfigError naming what is missing.

    `require_voice` is off for calls that only write a script and never speak.
    """
    base_url = _pick(base_url, "BASE_URL", None, str)
    model = _pick(model, "MODEL", None, str)
    voice = _pick(voice, "VOICE", None, str)

    key = _pick(api_key, "API_KEY", None, str)
    if not key:
        key = os.environ.get("OPENAI_API_KEY") or PLACEHOLDER_API_KEY

    # Every route falls back to the chat route, so one server can serve all of
    # them and a second one only needs the values it differs in.
    tts_base_url = _pick(tts_base_url, "TTS_BASE_URL", None, str) or base_url or ""
    tts_model = _pick(tts_model, "TTS_MODEL", None, str) or ""
    tts_key = _pick(tts_api_key, "TTS_API_KEY", None, str) or key
    stt_base_url = _pick(stt_base_url, "STT_BASE_URL", None, str) or base_url or ""
    stt_model = _pick(stt_model, "STT_MODEL", None, str) or ""
    stt_key = _pick(stt_api_key, "STT_API_KEY", None, str) or key

    missing = []
    if not base_url:
        missing.append("base_url (--base-url or PPTX_SCREENCAST_BASE_URL)")
    if not model:
        missing.append("model (--model or PPTX_SCREENCAST_MODEL)")
    if require_voice and not tts_model:
        missing.append("tts_model (--tts-model or PPTX_SCREENCAST_TTS_MODEL)")
    if require_voice and not (voice or "").strip():
        missing.append("voice (--voice or PPTX_SCREENCAST_VOICE)")
    if missing:
        raise ConfigError(
            "Missing: " + ", ".join(missing) + ". "
            "Example for a local server: base_url http://localhost:11434/v1, "
            "a chat model for the narration and a text-to-speech model with one "
            "of its voices for the audio."
        )

    settings = Settings(
        base_url=base_url,
        model=model,
        api_key=key,
        tts_base_url=tts_base_url,
        tts_model=tts_model,
        tts_api_key=tts_key,
        stt_base_url=stt_base_url,
        stt_model=stt_model,
        stt_api_key=stt_key,
        voice=str(voice or "").strip(),
        speed=_pick(speed, "SPEED", SPEED, float),
        language=str(_pick(language, "LANGUAGE", LANGUAGE, str)).strip() or LANGUAGE,
        subtitles=bool(_pick(subtitles, "SUBTITLES", False, _flag)),
        burn_in=bool(_pick(burn_in, "BURN_IN", False, _flag)),
        resolution=_pick(resolution, "RESOLUTION", RESOLUTION, int),
        fps=_pick(fps, "FPS", FPS, int),
        slide_pause=_pick(slide_pause, "SLIDE_PAUSE", SLIDE_PAUSE, float),
        crf=_pick(crf, "CRF", CRF, int),
        min_chars=_pick(min_chars, "MIN_CHARS", MIN_CHARS, int),
        max_chars=_pick(max_chars, "MAX_CHARS", MAX_CHARS, int),
        batch_size=_pick(batch_size, "BATCH_SIZE", BATCH_SIZE, int),
        batch_max_workers=_pick(batch_max_workers, "BATCH_MAX_WORKERS", BATCH_MAX_WORKERS, int),
        batch_timeout=_pick(batch_timeout, "BATCH_TIMEOUT", BATCH_TIMEOUT, float),
        max_slides=_pick(max_slides, "MAX_SLIDES", MAX_SLIDES, int),
        max_workers=_pick(max_workers, "MAX_WORKERS", MAX_WORKERS, int),
        work_dir=_pick(work_dir, "WORK_DIR", None, str),
    )
    _validate(settings)
    return settings


def _validate(s: Settings) -> None:
    positive = {
        "speed": s.speed,
        "resolution": s.resolution,
        "fps": s.fps,
        "min_chars": s.min_chars,
        "max_chars": s.max_chars,
        "batch_size": s.batch_size,
        "batch_max_workers": s.batch_max_workers,
        "batch_timeout": s.batch_timeout,
        "max_slides": s.max_slides,
        "max_workers": s.max_workers,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ConfigError(f"{name} must be greater than 0, but is {value}.")
    if s.slide_pause < 0:
        raise ConfigError("slide_pause must not be negative.")
    if not 0 <= s.crf <= 51:
        raise ConfigError(f"crf must be between 0 and 51, but is {s.crf}.")
    if s.max_chars < s.min_chars:
        raise ConfigError("max_chars must not be smaller than min_chars.")
    if s.burn_in and not s.subtitles:
        raise ConfigError("burn_in needs subtitles to be switched on as well.")
    if s.speed > 100:
        raise ConfigError(f"speed must be a factor such as 0.9 or 1.2, but is {s.speed}.")
