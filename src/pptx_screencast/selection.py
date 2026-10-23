"""Which slides go into the screencast and which keep their old audio."""

from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from .errors import ConfigError


@dataclass(frozen=True)
class Selection:
    """The three views on the same decision so nobody recomputes it."""

    clip_slides: List[int]
    excluded: Set[int]
    old_audio_allowed: Set[int]


def slide_selection(
    count: int,
    video_slides: Optional[List[int]],
    speak_again: Optional[List[int]],
) -> Selection:
    """None means all slides, numbers outside the range are dropped."""
    everything = set(range(count))
    included = everything if video_slides is None else {i for i in video_slides if i in everything}
    again = {i for i in (speak_again or []) if i in everything}
    return Selection(
        clip_slides=sorted(included),
        excluded=everything - included,
        old_audio_allowed=included - again,
    )


def clip_pairs(clip_slides: List[int], num_slides: int) -> List[Tuple[int, int]]:
    """Per clip the build position and the slide number that belong together."""
    return list(enumerate(i for i in clip_slides if i < num_slides))


def audio_slots(count: int, clip_slides: List[int]) -> List[bool]:
    """True only where new audio goes, otherwise the old one stays."""
    included = set(clip_slides)
    return [i in included for i in range(count)]


def slides_to_speak(clip_slides: List[int], scripts: List[str], already_there: Set[int]) -> int:
    """Counts the slides that still need real audio, neither pooled nor empty."""
    return sum(1 for i in clip_slides if i not in already_there and scripts[i].strip())


def parse_slides(text: str) -> List[int]:
    """Read '1-5,8' as slide indexes, counted from zero inside the package.

    People count slides from one, the package counts from zero.
    """
    numbers: List[int] = []
    for part in (text or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part.lstrip("-"):
            first, _, last = part.partition("-")
            try:
                start, end = int(first), int(last)
            except ValueError:
                raise ConfigError(f"{part!r} is not a slide range, write it like 1-5.")
            if start < 1 or end < start:
                raise ConfigError(f"{part!r} is not a slide range, write it like 1-5.")
            numbers.extend(range(start - 1, end))
            continue
        try:
            number = int(part)
        except ValueError:
            raise ConfigError(f"{part!r} is not a slide number, write it like 1-5,8.")
        if number < 1:
            raise ConfigError("Slide numbers start at 1.")
        numbers.append(number - 1)
    return sorted(set(numbers))
