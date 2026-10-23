"""File name helpers for the screencast output: readable stems and a timestamp."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .paths import safe_stem

logger = logging.getLogger(__name__)


def readable_stem(stem: str) -> str:
    """Turn a file name stem into plain text, so it can be translated."""
    return stem.replace("_", " ").replace("-", " ").strip()


def translate_stem(
    filename: str,
    target_lang: str,
    translator: Optional[Callable[[str, str], str]] = None,
) -> str:
    """The stem of the file name in the target language, or unchanged on failure."""
    stem = Path(str(filename).replace("\\", "/")).stem
    if not stem.strip():
        return "screencast"
    if translator is None or not target_lang:
        return safe_stem(stem)
    readable = readable_stem(stem)
    if not readable:
        return safe_stem(stem)
    try:
        translated = translator(readable, target_lang)
    except Exception as exc:  # the name is cosmetic, a failure must not stop the run
        logger.warning("The file name could not be translated: %s", exc)
        return safe_stem(stem)
    cleaned = safe_stem(translated.strip().replace(" ", "_"))
    return cleaned or safe_stem(stem)


def build_artifact_stem(stem: str, when: Optional[datetime] = None) -> str:
    """Append a timestamp (YYYY-MM-DD_HHMM), so names stay unique and sortable."""
    when = when or datetime.now()
    base = (stem or "screencast").strip() or "screencast"
    return f"{base}_{when.strftime('%Y-%m-%d_%H%M')}"
