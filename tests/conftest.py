"""Shared fixtures: a tiny deck on disk and the fake model server."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

DATA = Path(__file__).parent / "data"


@pytest.fixture
def sample_deck() -> Path:
    """The small deck that ships with the tests, four slides with notes."""
    return DATA / "sample.pptx"
