"""The voice of the screencast, one audio file per slide.

The speaking itself is done by doc2speech, which splits a long narration
into parts, sends them to any OpenAI-compatible `/audio/speech` endpoint and
joins the parts back into one file. Here the slides are walked through, a
server that is busy for a moment gets another try, and a slide that is
excluded or has no narration simply gets no file.

The speed is never sent to the server. Many servers lower the pitch of the
voice when they slow it down, which sounds hollow, so the speed is applied
later with ffmpeg.
"""

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Callable, List, Optional, Sequence, Set

from .config import Settings
from .errors import ModelError

logger = logging.getLogger(__name__)

# Waits before the second, third and fourth attempt of one slide.
RETRY_DELAYS = (2.0, 5.0, 10.0)

# Attempts doc2speech makes of its own inside one of ours. Zero, because the
# retry policy of a slide belongs here. Left at its default of two, a server
# that is down for good would be asked nine times for one slide instead of
# four, with none of the growing waits above between them.
TTS_MAX_RETRIES = 0

# Statuses of a server that was only busy for a moment.
_TRANSIENT_CODES = frozenset({"429", "500", "502", "503", "504"})

# The status in an error text, written either as "(503)" or as "code: 503".
_STATUS = re.compile(r"\((\d{3})\)|code:?\s*(\d{3})", re.IGNORECASE)

# Called with the number of finished slides, the total and the slide number.
Progress = Callable[[int, int, int], None]


def is_transient(error: Exception) -> bool:
    """True when another attempt can help.

    Servers and clients word their errors differently, so the bare "(503)" of
    one and the "Error code: 503" of the next both have to be recognised. A
    status that will not change, such as 401, is not transient.
    """
    text = str(error)
    for found in _STATUS.finditer(text):
        if (found.group(1) or found.group(2)) in _TRANSIENT_CODES:
            return True
    return False


def audio_path(tmp: Path, index: int) -> Path:
    """Where the audio of one slide lives while the video is built."""
    return tmp / f"slide_{index:03d}.mp3"


def speak_one(script: str, settings: Settings, sleep=time.sleep) -> bytes:
    """Voice one narration, giving a busy server up to three more tries.

    Everything doc2speech raises is a SpeechError, so nothing else can slip
    out of here but the ModelError this package reports.
    """
    from doc2speech import SpeechError, speak

    last_error: Optional[Exception] = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return speak(
                script,
                voice=settings.voice,
                base_url=settings.tts_base_url,
                model=settings.tts_model,
                api_key=settings.tts_api_key,
                language=settings.language,
                format="mp3",
                max_retries=TTS_MAX_RETRIES,
            )
        except SpeechError as e:
            last_error = e
            if attempt < len(RETRY_DELAYS) and is_transient(e):
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    "The voice failed (attempt %s/%s): %s, trying again in %ss",
                    attempt + 1, len(RETRY_DELAYS) + 1, e, delay,
                )
                sleep(delay)
                continue
            break
    raise ModelError(f"The narration could not be spoken: {last_error}")


def speak_all(
    scripts: Sequence[str],
    tmp: Path,
    settings: Settings,
    excluded: Optional[Set[int]] = None,
    on_slide_done: Optional[Progress] = None,
    max_workers: Optional[int] = None,
) -> List[Optional[Path]]:
    """One audio file per slide, None where a slide stays silent."""
    excluded = excluded or set()
    total = len(scripts)
    paths: List[Optional[Path]] = [None] * total
    done = [0]
    lock = Lock()

    def _report(index: int) -> None:
        if on_slide_done is None:
            return
        with lock:
            done[0] += 1
            on_slide_done(done[0], total, index)

    def _one(index: int) -> None:
        script = scripts[index]
        if index in excluded or not script.strip():
            logger.info("Slide %s/%s stays silent", index + 1, total)
            _report(index)
            return
        target = audio_path(tmp, index)
        target.write_bytes(speak_one(script, settings))
        logger.info("Slide %s/%s is spoken", index + 1, total)
        paths[index] = target
        _report(index)

    workers = max(1, min(max_workers or settings.max_workers, total))
    if workers == 1:
        for index in range(total):
            _one(index)
        return paths
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for _ in pool.map(_one, range(total)):
            pass
    return paths
