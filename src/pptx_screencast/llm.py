"""The chat client, assembled from the mixins that use it."""

from typing import Optional

from .client import make_chat_client
from .config import Settings
from .scripts import _ScriptsMixin
from .translate import _TranslateMixin


class _ChatBase:
    """The fields all mixins share, filled from the settings."""

    def __init__(self, settings: Settings, client=None):
        self._client = client if client is not None else make_chat_client(settings)
        self._model = settings.model
        self._base_url = settings.base_url
        # Extra fields some servers accept, empty means nothing is sent.
        self._extra_body: dict = {}
        # Batch settings for script generation.
        self._batch_size: int = settings.batch_size
        self._batch_max_workers: int = settings.batch_max_workers
        self._batch_timeout: float = settings.batch_timeout


class ChatClient(_TranslateMixin, _ScriptsMixin, _ChatBase):
    """Thin wrapper around an OpenAI-compatible chat endpoint."""


def make_llm(settings: Settings, client: Optional[object] = None) -> ChatClient:
    """The chat client of this run, or a ready-made one for the tests."""
    return ChatClient(settings, client=client)


__all__ = ["ChatClient", "make_llm"]
