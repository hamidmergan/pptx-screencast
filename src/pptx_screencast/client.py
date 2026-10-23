"""Clients for the OpenAI-compatible endpoints this package talks to.

Chat and speech recognition are called through the openai library. Speech is
not called here, doc2speech does that with its own client.
"""

from typing import Any

from .config import Settings

# A batch of slides keeps a request busy for minutes, while a connection that
# never comes up should be noticed in seconds.
CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 300.0
WRITE_TIMEOUT = 10.0
POOL_TIMEOUT = 10.0


def _timeout() -> Any:
    """A timeout per phase, or a plain read timeout when neither module is there.

    The openai library ships `httpx` in some versions and `httpx2` in others,
    so both names are tried before the simple value is used.
    """
    for name in ("httpx", "httpx2"):
        try:
            module = __import__(name)
        except ImportError:
            continue
        timeout = getattr(module, "Timeout", None)
        if timeout is None:
            continue
        return timeout(
            connect=CONNECT_TIMEOUT,
            read=READ_TIMEOUT,
            write=WRITE_TIMEOUT,
            pool=POOL_TIMEOUT,
        )
    return READ_TIMEOUT


def make_chat_client(settings: Settings):
    """The client for the chat model, used for the scripts and the translation."""
    from openai import OpenAI

    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=_timeout(),
    )


def make_stt_client(settings: Settings):
    """The client for the speech recognition model, used for the subtitle times."""
    from openai import OpenAI

    return OpenAI(
        api_key=settings.stt_api_key,
        base_url=settings.stt_base_url,
        timeout=_timeout(),
    )
