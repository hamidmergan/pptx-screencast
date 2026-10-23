"""Detects whether a model server turned a call down for good.

Only the final refusals are told apart here. Whether something is worth
another try is decided from the status code alone, in `stt.is_transient_error`
for the recogniser and on the error object itself for the voice. No message
text is read for that, because a message is free prose.
"""

from __future__ import annotations

import re

# Answers that stay the same however often the job asks again.
_REFUSAL_STATUSES = frozenset({400, 401, 403, 404})
_REFUSAL_TEXT = re.compile(r"(?:error code|client error)[: ']+(40[0134])\b")


def _status_of(e: BaseException) -> int | None:
    """The HTTP status an SDK or httpx error carries, None without one."""
    code = getattr(e, "status_code", None)
    if code is None:
        code = getattr(getattr(e, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def is_provider_refusal(e: BaseException | str) -> bool:
    """True when the provider turned the call down for good, a wrong key, a missing model or a rejected request."""
    if isinstance(e, str):
        return bool(_REFUSAL_TEXT.search(e.lower()))
    seen: set[int] = set()
    cur: BaseException | None = e
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _status_of(cur) in _REFUSAL_STATUSES or _REFUSAL_TEXT.search(str(cur).lower()):
            return True
        cur = cur.__cause__ or cur.__context__
    return False
