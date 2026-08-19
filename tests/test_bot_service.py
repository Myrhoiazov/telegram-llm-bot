from app.application.bot_service import FALLBACK_REPLY, BotService
from app.inference.base import InferenceError


class FakeResponder:
    def __init__(self, reply=None, error=None):
        self._reply = reply
        self._error = error

    def respond(self, text: str) -> str:
        if self._error is not None:
            raise self._error
        return self._reply


def test_handle_message_returns_responder_reply():
    service = BotService(FakeResponder(reply="hello back"))

    assert service.handle_message("hi") == "hello back"


def test_handle_message_returns_fallback_on_inference_error():
    service = BotService(FakeResponder(error=InferenceError("boom")))

    assert service.handle_message("hi") == FALLBACK_REPLY
