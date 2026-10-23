"""The system tools this package calls, and where to get them.

Everything is checked before the first long step, so a missing program is
reported in a second instead of after the slides were rendered.
"""

import shutil
from typing import List, Optional

from .errors import ToolError

# LibreOffice ships the command under two names, depending on the package.
SOFFICE_NAMES = ("libreoffice", "soffice")

HINTS = {
    "ffmpeg": "ffmpeg (apt install ffmpeg, brew install ffmpeg)",
    "ffprobe": "ffprobe, part of ffmpeg (apt install ffmpeg, brew install ffmpeg)",
    "libreoffice": "LibreOffice (apt install libreoffice-impress, brew install --cask libreoffice)",
    "pdftoppm": "pdftoppm, part of poppler (apt install poppler-utils, brew install poppler)",
    "pdfinfo": "pdfinfo, part of poppler (apt install poppler-utils, brew install poppler)",
}


def find_soffice() -> Optional[str]:
    """The LibreOffice command, under whichever name it is installed."""
    for name in SOFFICE_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def missing_tools(render: bool = True, video: bool = True) -> List[str]:
    """Names of the required tools that are not on PATH."""
    missing: List[str] = []
    if render:
        if find_soffice() is None:
            missing.append("libreoffice")
        missing.extend(name for name in ("pdftoppm", "pdfinfo") if not shutil.which(name))
    if video:
        missing.extend(name for name in ("ffmpeg", "ffprobe") if not shutil.which(name))
    return missing


def require_tools(render: bool = True, video: bool = True) -> None:
    """Raise ToolError naming every missing program and where to get it."""
    missing = missing_tools(render=render, video=video)
    if not missing:
        return
    raise ToolError(
        "Missing programs: " + ", ".join(HINTS.get(name, name) for name in missing)
    )
