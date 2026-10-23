"""Reading the times of the spoken words back out of the finished audio.

The cue times have to match what is really heard, and only the server that
produced the audio knows how long it turned out. So the audio goes once
through a speech recognition model, which answers with a segment per phrase.
"""

import json
import logging
import time
from typing import Optional

from .errors import ModelError

logger = logging.getLogger(__name__)

# Statuses worth another attempt that are not a 5xx.
RETRY_STATUS = frozenset({408, 429})


def status_of(e: BaseException) -> Optional[int]:
    """The HTTP status an SDK or transport error carries, None without one.

    The code is read off the object, never parsed out of a message text. A
    message is free prose: a 400 that happens to mention the word "timeout"
    would otherwise start a ladder of waits that cannot help.
    """
    seen: set = set()
    current: Optional[BaseException] = e
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for holder in (current, getattr(current, "response", None)):
            status = getattr(holder, "status_code", None)
            if isinstance(status, int):
                return status
        current = current.__cause__ or current.__context__
    return None


def _no_answer_arrived(e: BaseException) -> bool:
    """True for a refused connection or a timeout, which carry no status."""
    try:
        from openai import APIConnectionError
    except ImportError:  # pragma: no cover - openai is a hard dependency
        return False
    # APITimeoutError is a subclass of APIConnectionError.
    return isinstance(e, APIConnectionError)


def is_transient_error(e: Exception) -> bool:
    """True when another attempt can help.

    The verdict follows the status the server sent: 408, 429 and every 5xx
    are worth another try, every other answer is final. An error that never
    reached a server at all, a refused connection or a timeout, is transient
    too. Everything else, a bug in the answer or in this code, is final.
    """
    status = status_of(e)
    if status is not None:
        return status in RETRY_STATUS or 500 <= status < 600
    return _no_answer_arrived(e)


class Recogniser:
    """The speech recognition route, with a wait between the attempts.

    `deadline` is a `time.monotonic()` stamp for the whole subtitle step. A
    wait that would run past it is not taken, so a server that is up and
    rate limiting cannot hold a run for hours. Without a deadline the full
    ladder is walked, which is up to 1580 seconds for one file.
    """

    # Eight attempts in all, the tail covers a stubborn rate limit.
    BACKOFFS = (5, 15, 60, 180, 300, 420, 600)

    def __init__(self, client, model: str, deadline: Optional[float] = None):
        self._client = client
        self._model = model
        self._deadline = deadline

    def out_of_time(self) -> bool:
        """True when the step has used up the time it was given."""
        return self._deadline is not None and time.monotonic() >= self._deadline

    def _may_wait(self, seconds: float) -> bool:
        if self._deadline is None:
            return True
        return time.monotonic() + seconds < self._deadline

    def _verbose_call(self, file_path: str) -> tuple[list[dict], str]:
        """Ask the model and return the segments with the language it heard."""
        last_err: Exception | None = None
        for attempt in range(len(self.BACKOFFS) + 1):
            try:
                with open(file_path, "rb") as handle:
                    result = self._client.audio.transcriptions.create(
                        model=self._model,
                        file=handle,
                        response_format="verbose_json",
                    )
                if hasattr(result, "segments") and result.segments:
                    segments = [
                        {"start": s.start, "end": s.end, "text": s.text.strip()}
                        for s in result.segments if getattr(s, "text", "").strip()
                    ]
                    return segments, getattr(result, "language", "") or ""
                data = json.loads(str(result)) if isinstance(result, str) else result
                if isinstance(data, dict):
                    segments = [
                        {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                        for s in data.get("segments", []) if s.get("text", "").strip()
                    ]
                    return segments, data.get("language", "") or ""
                return [], ""
            except Exception as e:
                last_err = e
                if attempt < len(self.BACKOFFS) and is_transient_error(e):
                    wait = self.BACKOFFS[attempt]
                    if not self._may_wait(wait):
                        logger.warning(
                            "Speech recognition failed (attempt %s/%s): %s, and the "
                            "time for the subtitles is up, so it is not asked again",
                            attempt + 1, len(self.BACKOFFS) + 1, e,
                        )
                        break
                    logger.warning(
                        "Speech recognition failed (attempt %s/%s): %s, trying again in %ss",
                        attempt + 1, len(self.BACKOFFS) + 1, e, wait,
                    )
                    time.sleep(wait)
                    continue
                break
        raise ModelError(f"Speech recognition failed: {last_err}") from last_err

    def transcribe_verbose(self, file_path: str) -> tuple[list[dict], str]:
        """The segments of a file and the language they are in."""
        return self._verbose_call(file_path)
