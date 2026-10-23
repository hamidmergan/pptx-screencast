"""Rendering the slides to PNG. Needs LibreOffice, so it usually skips."""

from pathlib import Path

import pytest

from pptx_screencast.slides import pptx_to_images
from pptx_screencast.tools import missing_tools

MISSING = missing_tools(video=False)


@pytest.mark.skipif(MISSING, reason=f"not installed: {', '.join(MISSING)}")
def test_every_slide_becomes_one_image(sample_deck, tmp_path):
    images = pptx_to_images(sample_deck, tmp_path, dpi=50)
    assert len(images) == 4
    assert all(p.suffix == ".png" and p.stat().st_size > 0 for p in images)


@pytest.mark.skipif(MISSING, reason=f"not installed: {', '.join(MISSING)}")
def test_the_image_keeps_the_slide_ratio(sample_deck, tmp_path):
    from PIL import Image

    images = pptx_to_images(sample_deck, tmp_path, dpi=50)
    with Image.open(images[0]) as img:
        assert img.width / img.height == pytest.approx(16 / 9, abs=0.02)


def test_the_original_deck_is_not_touched(sample_deck, tmp_path):
    from pptx_screencast.slides import _apply_autofit_for_rendering

    copy = tmp_path / "deck.pptx"
    copy.write_bytes(sample_deck.read_bytes())
    before = copy.read_bytes()
    render_path = _apply_autofit_for_rendering(copy)
    assert render_path != copy
    assert copy.read_bytes() == before
    assert Path(render_path).exists()
