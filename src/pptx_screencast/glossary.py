"""A fixed term mapping for the narration and for the translation.

A glossary pins how a term has to come out: "Rechenzentrum" always becomes
"data centre", never "computing centre". The mapping is given to the chat
model as part of the instruction, so it holds for the narration that is
written and for a narration that is translated afterwards.

Two file formats are read, picked by what is in the file and not by the
extension:

* a JSON object, `{"Rechenzentrum": "data centre"}`
* one line per term, `Rechenzentrum = data centre`, with `#` for a comment
"""

import json
from pathlib import Path
from typing import Dict, Optional, Union

from .errors import ScriptError

PathLike = Union[str, Path]

# What may stand between a term and its replacement in the line format.
_SEPARATORS = ("=", "->", "\t")


def glossary_hint(glossary: Optional[Dict[str, str]]) -> str:
    """The part of the instruction that names the terms, empty without any."""
    if not glossary:
        return ""
    lines = "\n".join(f"- {k} → {v}" for k, v in glossary.items())
    return f"Use the following terminology consistently in your output:\n{lines}\n\n"


def parse_glossary(raw: str) -> Dict[str, str]:
    """Read a glossary from JSON or from one term per line."""
    text = (raw or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ScriptError(f"The glossary is not valid JSON: {exc}")
        if not isinstance(data, dict):
            raise ScriptError("A JSON glossary has to be an object of term to replacement.")
        return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip()}

    found: Dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        for separator in _SEPARATORS:
            if separator in entry:
                term, _, replacement = entry.partition(separator)
                if term.strip() and replacement.strip():
                    found[term.strip()] = replacement.strip()
                    break
                raise ScriptError(
                    f"Line {number} of the glossary has no term or no replacement: {entry!r}"
                )
        else:
            raise ScriptError(
                f"Line {number} of the glossary has no separator. "
                f"Write it like 'term = replacement': {entry!r}"
            )
    return found


def read_glossary(path: PathLike) -> Dict[str, str]:
    """The glossary of a file, or a ScriptError naming what is wrong with it."""
    target = Path(path)
    try:
        raw = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScriptError(f"The glossary {target} could not be read: {exc}")
    glossary = parse_glossary(raw)
    if not glossary:
        raise ScriptError(f"The glossary {target} holds no term.")
    return glossary


__all__ = ["glossary_hint", "parse_glossary", "read_glossary"]
