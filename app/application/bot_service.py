"""Main use case: turn one incoming user message into one reply."""
from __future__ import annotations

import logging

from app.application.responder import Responder
from app.inference.base import InferenceError

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "Сейчас не получилось получить ответ от локальной модели. "
    "Попробуйте еще раз чуть позже."
)


class BotService:
    def __init__(self, responder: Responder) -> None:
        self._responder = responder

    def handle_message(self, text: str) -> str:
        try:
            return self._responder.respond(text)
        except InferenceError:
            logger.exception("Inference failed while handling message")
            return FALLBACK_REPLY
