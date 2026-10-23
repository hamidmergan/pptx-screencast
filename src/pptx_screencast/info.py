"""The info file that goes into the download: what is inside the video.

A screencast is handed on, often months later. The info file says what it
was made from and with, so nobody has to guess.
"""

from datetime import datetime
from typing import Optional

from .outro import NOTICE_TEXT


def duration_text(seconds: float) -> str:
    """A duration the way you would say it out loud."""
    total = round(seconds or 0)
    if total < 60:
        return f"{total} s"
    if total < 3600:
        return f"{total // 60} min {total % 60} s"
    return f"{total // 3600} h {(total % 3600) // 60} min"


def _number(value) -> str:
    return f"{int(value):,}"


def _decimal(value) -> str:
    return f"{float(value):.1f}"


def build_info(
    name: str,
    *,
    slides: int,
    characters: int,
    language: str = "",
    voice: str = "",
    speed: Optional[float] = None,
    slide_pause: Optional[float] = None,
    subtitles: bool = False,
    duration: Optional[float] = None,
    when: Optional[datetime] = None,
) -> str:
    """The text of the info file."""
    when = when or datetime.now()
    lines = [
        f"Screencast: {name}",
        f"Created on: {when.strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Slides: {_number(slides)}",
        f"Characters in the narration: {_number(characters)}",
    ]
    if language:
        lines.append(f"Language: {language}")
    if voice:
        lines.append(f"Voice: {voice}")
    if speed is not None:
        lines.append(f"Speed: {_decimal(speed)}")
    if slide_pause is not None:
        lines.append(f"Pause between slides: {_decimal(slide_pause)} seconds")
    lines.append(f"Subtitles: {'yes' if subtitles else 'no'}")
    if duration is not None:
        lines.append(f"Length: {duration_text(duration)}")
    lines += ["", NOTICE_TEXT]
    return "\n".join(lines) + "\n"
