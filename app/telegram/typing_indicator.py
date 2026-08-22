"""Background 'typing...' chat action while waiting for a reply."""
from __future__ import annotations

import logging
import threading

from app.telegram.client import TelegramAPIError, TelegramClient

logger = logging.getLogger(__name__)


class TypingIndicator:
    """Resends the Telegram 'typing' chat action on an interval until closed."""

    def __init__(self, client: TelegramClient, chat_id: int, interval_seconds: int) -> None:
        self._client = client
        self._chat_id = chat_id
        self._interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "TypingIndicator":
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._client.send_chat_action(self._chat_id, "typing")
            except TelegramAPIError:
                logger.warning("Failed to send typing action for chat %s", self._chat_id)
            self._stop_event.wait(self._interval_seconds)
