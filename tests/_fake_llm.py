"""A chat client that answers from a list, so no server is needed."""

from pptx_screencast.scripts import _ScriptsMixin
from pptx_screencast.translate import _TranslateMixin


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = FakeMessage(content)
        self.finish_reason = finish_reason


class FakeResponse:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [FakeChoice(content, finish_reason)]


class FakeCompletions:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls: list[list[dict]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs["messages"])
        reply = self._replies.pop(0) if self._replies else "..."
        if isinstance(reply, Exception):
            raise reply
        return FakeResponse(reply)


class FakeClient:
    def __init__(self, replies):
        self.chat = type("Chat", (), {"completions": FakeCompletions(replies)})()


class ScriptClient(_TranslateMixin, _ScriptsMixin):
    """Only the script logic, without a real provider."""

    def __init__(self, replies, batch_size=3):
        self._client = FakeClient(replies)
        self._model = "test-model"
        self._extra_body = {}
        self._batch_size = batch_size
        self._batch_max_workers = 1
        self._batch_timeout = 5.0

    @property
    def calls(self):
        return self._client.chat.completions.calls


def slides(n: int) -> list[str]:
    return [f"Slide text {i + 1}" for i in range(n)]
