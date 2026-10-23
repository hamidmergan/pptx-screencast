"""Reading the times of the spoken words back out of the finished audio.

The cue times have to match what is really heard, and only the server that
produced the audio knows how long it turned out. So the audio goes once
through a speech recognition model, which answers with a segment per phrase.
"""

import json
import logging
import time

logger = logging.getLogger(__name__)


def is_transient_error(e: Exception) -> bool:
    """Upstream failures worth another attempt: 5xx, 429, timeouts, lost connections."""
    status = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    if isinstance(status, int) and (500 <= status < 600 or status == 429):
        return True
    msg = str(e).lower()
    return any(kw in msg for kw in (
        "internal server error", "bad gateway", "service unavailable",
        "gateway timeout", "timeout", "connection", "temporarily",
        "rate limit", "429",
    ))


class Recogniser:
    """The speech recognition route, with a wait between the attempts."""

    # Eight attempts in all, the tail covers a stubborn rate limit.
    BACKOFFS = (5, 15, 60, 180, 300, 420, 600)

    def __init__(self, client, model: str):
        self._client = client
        self._model = model

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
                    logger.warning(
                        "Speech recognition failed (attempt %s/%s): %s, trying again in %ss",
                        attempt + 1, len(self.BACKOFFS) + 1, e, wait,
                    )
                    time.sleep(wait)
                    continue
                break
        raise RuntimeError(f"Speech recognition failed: {last_err}") from last_err

    def transcribe_verbose(self, file_path: str) -> tuple[list[dict], str]:
        """The segments of a file and the language they are in."""
        return self._verbose_call(file_path)
