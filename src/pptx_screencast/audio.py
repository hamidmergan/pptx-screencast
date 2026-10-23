"""The voice of the screencast, one audio file per slide.

The speaking itself is done by doc2speech, which splits a long narration into
parts, spells digits out, sends one request per part to any OpenAI-compatible
`/audio/speech` endpoint and joins the parts back into one file without
re-encoding.

A narration of this package may be up to `max_chars` characters long, so one
slide is several requests. The retry ladder therefore sits on the part and not
on the slide: one part that comes back badly costs one more request, not the
whole slide again. The parts of all slides share one pool, so a busy server
never sees more open requests than `max_workers`, however many slides are in
flight.

Every value doc2speech works with is passed in, so a `DOC2SPEECH_*` variable
cannot change the voice, the chunk size or the number of attempts behind this
package's back.

The speed is not sent to the server. Many servers lower the pitch of the
voice when they slow it down, which sounds hollow, so the speed is applied
later with ffmpeg.
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, Sequence, Set

from .config import Settings
from .errors import ModelError

logger = logging.getLogger(__name__)

# Waits before the second, third and fourth attempt of one part.
RETRY_DELAYS = (2.0, 5.0, 10.0)

# Characters per request. Many servers give up on a request after about
# 60 seconds of audio, so a long narration goes out in short parts. Passed to
# doc2speech explicitly, so splitting and sending always agree.
CHUNK_CHARS = 400

# Seconds one request may take.
REQUEST_TIMEOUT = 90.0

# Format of the audio per slide.
AUDIO_FORMAT = "mp3"

# Attempts doc2speech makes of its own inside one of ours. Zero, because the
# retry policy of a part belongs here, with the growing waits above. Left at
# its default of two, a part would be asked nine times instead of four.
TTS_MAX_RETRIES = 0

# A speed doc2speech reads from its own environment would be sent to the
# server on top of the local one, so it is pointed out once.
_SPEED_ENV = "DOC2SPEECH_SPEED"

# Called with the number of finished slides, the total and the slide number.
Progress = Callable[[int, int, int], None]


def is_transient(error: Exception) -> bool:
    """True when another attempt can help.

    doc2speech decides this itself and says so on the error, so no message
    text is read here. A timeout and a refused connection carry no status and
    count as transient, 408, 429 and every 5xx do as well, every other answer
    is final.

    An error without that verdict is final too. A missing setting, an empty
    text or audio that could not be joined does not change on another try.
    """
    verdict = getattr(error, "transient", None)
    return verdict if isinstance(verdict, bool) else False


def audio_path(tmp: Path, index: int) -> Path:
    """Where the audio of one slide lives while the video is built."""
    return tmp / f"slide_{index:03d}.mp3"


def split_narration(script: str) -> List[str]:
    """The parts one narration goes out in, one request per part."""
    from doc2speech import split_text

    return [part for part in split_text(script, CHUNK_CHARS) if part.strip()]


def _warn_about_a_foreign_speed() -> None:
    if os.environ.get(_SPEED_ENV, "").strip():
        logger.warning(
            "%s is set, so a speed is sent to the speech server on top of the "
            "local one. Unset it and use --speed or PPTX_SCREENCAST_SPEED.",
            _SPEED_ENV,
        )


class Abort:
    """Once one part has given up, the rest of the run stops asking.

    Without this a server that is down would still be asked four times for
    every part that was already on its way, so one slide could cost four
    times as many requests as the first failure needed to find out.
    """

    def __init__(self) -> None:
        self._error: Optional[Exception] = None
        self._lock = Lock()

    @property
    def error(self) -> Optional[Exception]:
        return self._error

    def give_up(self, error: Optional[Exception]) -> None:
        with self._lock:
            if self._error is None:
                self._error = error


def speak_part(
    part: str,
    settings: Settings,
    sleep=time.sleep,
    where: str = "",
    abort: Optional[Abort] = None,
) -> bytes:
    """Voice one part, giving a busy server up to three more tries.

    One call is exactly one request per attempt. Everything doc2speech raises
    is a SpeechError, so nothing else can slip out of here but the ModelError
    this package reports.
    """
    from doc2speech import SpeechError, speak

    if abort is not None and abort.error is not None:
        raise ModelError(f"The narration could not be spoken{where}: {abort.error}")

    last_error: Optional[Exception] = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            return speak(
                part,
                voice=settings.voice,
                base_url=settings.tts_base_url,
                model=settings.tts_model,
                api_key=settings.tts_api_key,
                language=settings.language,
                format=AUDIO_FORMAT,
                max_chars_per_chunk=CHUNK_CHARS,
                max_chars=max(len(part), CHUNK_CHARS),
                concurrency=1,
                timeout=REQUEST_TIMEOUT,
                max_retries=TTS_MAX_RETRIES,
            )
        except SpeechError as e:
            last_error = e
            still_running = abort is None or abort.error is None
            if attempt < len(RETRY_DELAYS) and is_transient(e) and still_running:
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    "The voice failed%s (attempt %s/%s): %s, trying again in %ss",
                    where, attempt + 1, len(RETRY_DELAYS) + 1, e, delay,
                )
                sleep(delay)
                continue
            break
    if abort is not None:
        abort.give_up(last_error)
        last_error = abort.error or last_error
    raise ModelError(f"The narration could not be spoken{where}: {last_error}")


def join_parts(parts: Sequence[bytes]) -> bytes:
    """The parts of one narration as one audio file, without re-encoding."""
    # doc2speech joins its own parts with this, so both sides stay in step.
    from doc2speech import SpeechError
    from doc2speech.audio import join

    try:
        return join(list(parts), AUDIO_FORMAT)
    except SpeechError as e:
        raise ModelError(f"The spoken parts could not be joined: {e}")


def speak_one(script: str, settings: Settings, sleep=time.sleep) -> bytes:
    """Voice one narration, part by part, and return the whole audio."""
    _warn_about_a_foreign_speed()
    parts = split_narration(script)
    if not parts:
        raise ModelError("The narration is empty, there is nothing to speak.")
    spoken = [speak_part(part, settings, sleep) for part in parts]
    return join_parts(spoken)


def speak_all(
    scripts: Sequence[str],
    tmp: Path,
    settings: Settings,
    excluded: Optional[Set[int]] = None,
    on_slide_done: Optional[Progress] = None,
    max_workers: Optional[int] = None,
) -> List[Optional[Path]]:
    """One audio file per slide, None where a slide stays silent.

    Only the slides that were not excluded are counted and reported, so the
    total of the progress is the number of slides this call works on.
    """
    excluded = excluded or set()
    paths: List[Optional[Path]] = [None] * len(scripts)
    mine = [index for index in range(len(scripts)) if index not in excluded]
    total = len(mine)
    done = [0]
    lock = Lock()
    _warn_about_a_foreign_speed()

    def _report(index: int) -> None:
        if on_slide_done is None:
            return
        with lock:
            done[0] += 1
            on_slide_done(done[0], total, index)

    plan: Dict[int, List[str]] = {}
    for index in mine:
        parts = split_narration(scripts[index])
        if parts:
            plan[index] = parts
    requests = sum(len(parts) for parts in plan.values())
    workers = max(1, min(max_workers or settings.max_workers, requests or 1))

    # One pool over the parts of all slides, so the server never sees more
    # than `workers` open requests, and the slides are still released in
    # order, which keeps a progress display moving front to back.
    futures: Dict[int, list] = {}
    abort = Abort()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        try:
            for index, parts in plan.items():
                futures[index] = [
                    pool.submit(
                        speak_part, part, settings, time.sleep,
                        f" for slide {index + 1}, part {number + 1}/{len(parts)}",
                        abort,
                    )
                    for number, part in enumerate(parts)
                ]
            for index in mine:
                if index not in futures:
                    logger.info("Slide %s/%s stays silent", index + 1, total)
                    _report(index)
                    continue
                spoken = [future.result() for future in futures[index]]
                target = audio_path(tmp, index)
                target.write_bytes(join_parts(spoken))
                paths[index] = target
                logger.info(
                    "Slide %s/%s is spoken (%s request(s))", index + 1, total, len(spoken)
                )
                _report(index)
        except BaseException:
            for rest in futures.values():
                for future in rest:
                    future.cancel()
            raise
    return paths
