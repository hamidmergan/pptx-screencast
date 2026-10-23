"""The notice slide that opens and closes the video.

A screencast whose voice and narration come from a model should say so, so
the same plain slide is put in front of the deck and behind it, and the same
sentence goes into the metadata of the MP4. The slide is drawn here instead
of shipped as a picture, so it has the size of the deck and can carry any
text.
"""

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

NOTICE_TEXT = "This video was created with AI assistance."

# Share of the slide width the text may use.
_TEXT_WIDTH = 0.8

# Share of the slide height one line of text is tall.
_LINE_HEIGHT = 0.07

BACKGROUND = "white"
FOREGROUND = "#222222"

# Fonts that are likely to be on a Linux image or a Mac, in that order.
_FONT_FILES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def _font(size: int):
    """A real font where one is installed, the built-in one otherwise."""
    for path in _FONT_FILES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, max(size, 1))
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(draw, text: str, font, max_width: float) -> List[str]:
    """Greedy word wrap, a single overlong word stays on its own line."""
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and draw.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def create_outro_image(
    width: int, height: int, output_path: Path, text: str = NOTICE_TEXT
) -> Path:
    """Draw the notice slide at exactly this size and return the path."""
    canvas = Image.new("RGB", (max(width, 16), max(height, 16)), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    size = max(12, int(canvas.height * _LINE_HEIGHT))
    font = _font(size)
    lines = _wrap(draw, text, font, canvas.width * _TEXT_WIDTH)
    line_height = size * 1.4
    top = (canvas.height - line_height * len(lines)) / 2
    for index, line in enumerate(lines):
        line_width = draw.textlength(line, font=font)
        draw.text(
            ((canvas.width - line_width) / 2, top + index * line_height),
            line,
            fill=FOREGROUND,
            font=font,
        )
    canvas.save(output_path, "PNG")
    return output_path


def get_image_dimensions(image_path: Path) -> Tuple[int, int]:
    """Width and height of an image."""
    with Image.open(image_path) as img:
        return img.size


def frame_clips(
    clips: Sequence[Path], has_speech: Sequence[bool], notice: Optional[Path]
) -> Tuple[List[Path], List[bool]]:
    """Put the notice clip before and after the slides, counting it as silent."""
    if notice is None:
        return list(clips), list(has_speech)
    return [notice, *clips, notice], [False, *has_speech, False]
