"""Parsing of raw Telegram getUpdates payloads into internal message objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextMessage:
    update_id: int
    chat_id: int
    text: str


@dataclass(frozen=True)
class VoiceMessage:
    update_id: int
    chat_id: int
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: str | None = None


@dataclass(frozen=True)
class CallbackQuery:
    update_id: int
    callback_query_id: str
    chat_id: int
    data: str


UpdateEvent = TextMessage | VoiceMessage | CallbackQuery


SUPPORTED_CALLBACK_DATA = {"mode:new", "mode:voice"}


def parse_updates(payload: dict) -> list[UpdateEvent]:
    messages: list[UpdateEvent] = []
    for update in payload.get("result", []):
        message = _extract_update_event(update)
        if message is not None:
            messages.append(message)
    return messages


def _extract_update_event(update: dict) -> UpdateEvent | None:
    if not isinstance(update, dict):
        return None

    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return None

    callback = _extract_callback_query(update, update_id)
    if callback is not None:
        return callback

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
    if isinstance(text, str) and text.strip():
        return TextMessage(update_id=update_id, chat_id=chat_id, text=text)

    voice = message.get("voice")
    if isinstance(voice, dict):
        file_id = voice.get("file_id")
        file_unique_id = voice.get("file_unique_id")
        duration = voice.get("duration")
        mime_type = voice.get("mime_type")
        if (
            isinstance(file_id, str)
            and file_id
            and isinstance(file_unique_id, str)
            and file_unique_id
            and isinstance(duration, int)
        ):
            return VoiceMessage(
                update_id=update_id,
                chat_id=chat_id,
                file_id=file_id,
                file_unique_id=file_unique_id,
                duration=duration,
                mime_type=mime_type if isinstance(mime_type, str) else None,
            )

    return None


def _extract_callback_query(update: dict, update_id: int) -> CallbackQuery | None:
    callback = update.get("callback_query")
    if not isinstance(callback, dict):
        return None

    callback_query_id = callback.get("id")
    data = callback.get("data")
    message = callback.get("message")
    if (
        not isinstance(callback_query_id, str)
        or not callback_query_id
        or not isinstance(data, str)
        or data not in SUPPORTED_CALLBACK_DATA
        or not isinstance(message, dict)
    ):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None
    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return None

    return CallbackQuery(
        update_id=update_id,
        callback_query_id=callback_query_id,
        chat_id=chat_id,
        data=data,
    )
