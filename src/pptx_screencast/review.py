"""Which slides a translation left as they were.

A chat model that translates a deck sometimes hands a slide back unchanged,
because it thought the text was already in the target language or because it
simply skipped it. That is not an error and nothing can be retried blindly,
but the person reading the result should be told which slides to look at.

Very short texts are left out of the comparison. A heading of two words is
often the same in both languages, so reporting it would only be noise.
"""

from typing import List, Sequence

# Words a text needs before an unchanged result says anything.
MIN_WORDS = 6


def find_unchanged_slides(
    before: Sequence[str],
    after: Sequence[str],
    min_words: int = MIN_WORDS,
) -> List[int]:
    """Indexes of the slides whose text came back exactly as it went in.

    Counted from zero. Empty slides and texts under `min_words` words are
    skipped, and so is a slide that has no counterpart in the result.
    """
    unchanged: List[int] = []
    for index, original in enumerate(before):
        if index >= len(after):
            break
        text = (original or "").strip()
        if len(text.split()) < min_words:
            continue
        if text == (after[index] or "").strip():
            unchanged.append(index)
    return unchanged


__all__ = ["MIN_WORDS", "find_unchanged_slides"]
