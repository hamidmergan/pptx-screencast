"""The narration as a Markdown file, one heading per slide.

The file is meant to be read and corrected by hand before the deck is voiced,
so it stays as plain as a Markdown file can be:

    # deck

    ## Slide 1

    Welcome to this short tour.

    ## Slide 2

    The first point is the simplest one.

A slide that stays silent keeps its heading and has no text under it.

On reading, the slide headings are the ones on the shallowest level below
the top, so a single `#` line stays the title of the file and is not spoken.
A file whose headings are all on the top level has no title and every
heading opens a slide. Headings deeper than the slide level stay in the text
of their slide.
"""

import re
from pathlib import Path
from typing import List, Optional, Sequence, Union

from .errors import ScriptError

PathLike = Union[str, Path]

# A Markdown heading, with its level and its text.
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s*(.*?)\s*#*\s*$")

# "Slide 7" or "Slide 7: the costs", the number is the only part that counts.
_NUMBERED = re.compile(r"^slide\s+(\d+)\b", re.IGNORECASE)


def heading(index: int) -> str:
    """The heading of a slide, counted from one the way people count."""
    return f"## Slide {index + 1}"


def render_script_file(scripts: Sequence[str], title: str = "") -> str:
    """The Markdown text of a script file, ending with one newline."""
    blocks: List[str] = []
    if title.strip():
        blocks.append(f"# {title.strip()}")
    for index, script in enumerate(scripts):
        blocks.append(heading(index))
        text = (script or "").strip()
        if text:
            blocks.append(text)
    return "\n\n".join(blocks) + "\n"


def write_script_file(scripts: Sequence[str], path: PathLike, title: str = "") -> Path:
    """Write the script file and return the path it was written to."""
    target = Path(path)
    if target.parent and not target.parent.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_script_file(scripts, title), encoding="utf-8")
    return target


def slide_level(text: str) -> int:
    """The heading level that opens a slide in this file."""
    levels = {len(m.group(1)) for m in (_HEADING.match(line) for line in (text or "").splitlines()) if m}
    below_top = {level for level in levels if level > 1}
    return min(below_top) if below_top else 1


def parse_script_file(text: str) -> List[str]:
    """The narration per slide, in the order of the slide headings."""
    level = slide_level(text)
    scripts: List[str] = []
    current: Optional[List[str]] = None
    for line in (text or "").splitlines():
        match = _HEADING.match(line)
        if match and len(match.group(1)) == level:
            if current is not None:
                scripts.append("\n".join(current).strip())
            current = []
            continue
        if current is not None:
            current.append(line)
    if current is not None:
        scripts.append("\n".join(current).strip())
    if not scripts:
        raise ScriptError(
            "The script file has no slide heading. Write one heading per "
            "slide, for example '## Slide 1'."
        )
    # A file that is only a title holds no narration at all.
    if len(scripts) == 1 and not scripts[0]:
        raise ScriptError("The script file holds no narration.")
    return scripts


def read_script_file(path: PathLike, count: Optional[int] = None) -> List[str]:
    """Read a script file, and check the number of slides when it is known."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScriptError(f"The script file {source} cannot be read: {exc}")
    scripts = parse_script_file(text)
    if count is not None and len(scripts) != count:
        raise ScriptError(
            f"The script file has {len(scripts)} slide(s), the deck has {count}. "
            "Add or remove headings so both match."
        )
    return scripts


def numbered_headings(text: str) -> List[int]:
    """The slide numbers a file names, for a hint when the count is off."""
    level = slide_level(text)
    numbers: List[int] = []
    for line in (text or "").splitlines():
        match = _HEADING.match(line)
        if not match or len(match.group(1)) != level:
            continue
        numbered = _NUMBERED.match(match.group(2))
        if numbered:
            numbers.append(int(numbered.group(1)))
    return numbers
