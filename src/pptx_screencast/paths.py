"""Where the intermediate files of a run live, and how the output is named.

Slide images, audio per slide and the clips are intermediate files. Without a
work directory they go into a temporary folder that is deleted at the end.
With one, they stay, which makes a failed run easy to look at.
"""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

# Characters a file name may keep, everything else is dropped.
_KEEP = " -_."

# Longest stem of a generated name.
_MAX_STEM = 80


def safe_stem(filename: str) -> str:
    """A file name stem that is safe on every system."""
    stem = Path(str(filename).replace("\\", "/")).stem
    cleaned = "".join(ch for ch in stem if ch.isalnum() or ch in _KEEP).strip()
    return cleaned[:_MAX_STEM] or "screencast"


def free_path(path: Path) -> Path:
    """The path itself, or 'name (1).mp4', 'name (2).mp4', if it is taken."""
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


@contextmanager
def work_dir(configured: Optional[str] = None, keep: bool = False) -> Iterator[Path]:
    """The folder for the intermediate files of one run.

    A configured folder is created and kept. Without one a temporary folder is
    used and removed again, unless `keep` says otherwise.
    """
    if configured:
        target = Path(configured).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        yield target
        return
    created = Path(tempfile.mkdtemp(prefix="pptx-screencast-"))
    try:
        yield created
    finally:
        if not keep:
            shutil.rmtree(created, ignore_errors=True)
