"""Extra text per slide, to make a narration concrete.

A slide often holds three bullet points while the lecturer's own handout
holds the definition, the example and the figure behind them. Material is
that extra text, given per slide. It goes into the prompt between
`[MATERIAL]` and `[END MATERIAL]` and the model may use it to explain the
slide's own points, never to add a topic of its own.

Two things are guarded here:

* the batch separators. The slides of one request are separated by `===` and
  the answers by `|||`, so material that holds either of them could forge a
  separator and shift every script of the batch by one slide.
* the length. A model has a limited window, and material is the part that
  grows without bound, so it is trimmed per slide.

The text itself has to be supplied by the caller. This package reads PPTX
files and nothing else, so turning a PDF or a Word file into text is the
caller's job.
"""

import logging
import re
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

# Characters of material one slide may carry into the prompt.
MATERIAL_CHARS = 4000

# The separators of a batch, which must never appear inside material.
_SEPARATORS = ("|||", "===")

# Where a trimmed piece may end, in this order of preference.
_SENTENCE_END = (". ", "! ", "? ", ".\n", "!\n", "?\n")


def clean_material(text: str) -> str:
    """Material without the batch separators and without stray blank lines."""
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    for separator in _SEPARATORS:
        cleaned = cleaned.replace(separator, " ")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def material_slice(text: str, limit: int = MATERIAL_CHARS) -> str:
    """The first `limit` characters, cut at a sentence or a word if possible."""
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    head = text[:limit]
    for end in _SENTENCE_END:
        position = head.rfind(end)
        if position > limit // 2:
            return head[: position + len(end)].strip()
    position = head.rfind(" ")
    return (head[:position] if position > limit // 2 else head).strip()


def prepare_materials(
    materials: Optional[Sequence[str]],
    count: int,
    limit: int = MATERIAL_CHARS,
) -> Optional[List[str]]:
    """One cleaned and trimmed entry per slide, or None without any material.

    Shorter input is padded with empty entries and longer input is cut, so the
    result always lines up with the slides.
    """
    if not materials:
        return None
    prepared = [material_slice(clean_material(text or ""), limit) for text in materials]
    if len(prepared) < count:
        prepared.extend([""] * (count - len(prepared)))
    prepared = prepared[:count]
    if not any(prepared):
        return None
    dropped = sum(
        1 for original, kept in zip(materials, prepared)
        if len(clean_material(original or "")) > len(kept)
    )
    if dropped:
        logger.info(
            "The material of %s slide(s) was trimmed to %s characters", dropped, limit
        )
    return prepared


__all__ = ["MATERIAL_CHARS", "clean_material", "material_slice", "prepare_materials"]
