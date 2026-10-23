"""Where the narration of a deck comes from.

Three sources, in the order the caller chooses them:

* a script file that was written and corrected by hand
* the speaker notes of the deck
* the chat model, which writes one narration per slide from the slide text

Whatever the source, the result is one entry per visible slide, in slide
order, and an entry may be empty for a slide that stays silent.
"""

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Union

from .errors import ScriptError
from .script_file import read_script_file

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


def generate_all_scripts(
    slide_texts: List[str],
    llm_client,
    glossary: Optional[dict] = None,
    add_greeting: bool = True,
    add_closing: bool = True,
    min_chars: int = 1500,
    max_chars: int = 2000,
    source_lang: str = "DE",
    target_lang: str = "EN-US",
    materials: Optional[List[str]] = None,
) -> List[str]:
    """One narration per slide from the chat model."""
    try:
        scripts = llm_client.generate_scripts_batch(
            slide_texts, glossary, add_greeting, add_closing,
            min_chars=min_chars, max_chars=max_chars,
            source_lang=source_lang, target_lang=target_lang,
            materials=materials,
        )
        logger.info("Batch script generation completed for %s slides", len(slide_texts))
        return scripts
    except RuntimeError as e:
        logger.error("Batch script generation failed: %s", e)
        raise ScriptError(f"Script generation failed: {e}")


def scripts_from_notes(notes: Sequence[str], count: Optional[int] = None) -> List[str]:
    """The speaker notes as the narration, one entry per slide."""
    scripts = [(note or "").strip() for note in notes]
    if count is not None:
        if len(scripts) < count:
            scripts.extend([""] * (count - len(scripts)))
        scripts = scripts[:count]
    if not any(scripts):
        raise ScriptError(
            "No slide of the deck has speaker notes. Drop --notes to let the "
            "model write the narration, or add notes to the deck."
        )
    return scripts


def scripts_from_file(path: PathLike, count: Optional[int] = None) -> List[str]:
    """The narration of a script file that was written before."""
    return read_script_file(path, count)


def translate_scripts(
    scripts: Sequence[str],
    target_lang: str,
    llm_client,
    max_workers: Optional[int] = None,
    glossary: Optional[dict] = None,
) -> List[str]:
    """The narration in another language, empty slides stay empty.

    The glossary holds here as well, so a term that was pinned while the
    narration was written keeps its wording in the other language.
    """
    if not (target_lang or "").strip():
        return list(scripts)
    return llm_client.translate_batch(
        list(scripts), target_lang, max_workers=max_workers, glossary=glossary
    )


def check_count(scripts: Sequence[str], count: int) -> List[str]:
    """Make sure there is exactly one narration per slide."""
    if len(scripts) != count:
        raise ScriptError(
            f"There are {len(scripts)} narration(s) for {count} slide(s). "
            "Every slide needs exactly one, an empty one for a silent slide."
        )
    return list(scripts)
