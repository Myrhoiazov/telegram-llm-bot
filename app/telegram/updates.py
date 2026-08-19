"""Parsing of raw Telegram getUpdates payloads into internal message objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextMessage:
    update_id: int
    chat_id: int
    text: str


def parse_updates(payload: dict) -> list[TextMessage]:
    messages: list[TextMessage] = []
    for update in payload.get("result", []):
        message = _extract_text_message(update)
        if message is not None:
            messages.append(message)
    return messages


def _extract_text_message(update: dict) -> TextMessage | None:
    if not isinstance(update, dict):
        return None

    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return None

    message = update.get("message")
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return None

    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None

    return TextMessage(update_id=update_id, chat_id=chat_id, text=text)
