"""Low-level Telegram Bot API HTTP calls: getUpdates and sendMessage."""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    """Raised when a Telegram API call fails, times out, or returns an error."""


class TelegramClient:
    def __init__(
        self,
        token: str,
        poll_timeout_seconds: int,
        request_timeout_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = f"https://api.telegram.org/bot{token}"
        self._poll_timeout_seconds = poll_timeout_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._session = session or requests.Session()

    def get_updates(self, offset: int | None) -> dict:
        params = {"timeout": self._poll_timeout_seconds}
        if offset is not None:
            params["offset"] = offset
        http_timeout = self._poll_timeout_seconds + self._request_timeout_seconds
        return self._call("getUpdates", params=params, timeout=http_timeout)

    def send_message(self, chat_id: int, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text}
        self._call("sendMessage", json_body=payload, timeout=self._request_timeout_seconds)

    def _call(self, method: str, timeout: int, params=None, json_body=None) -> dict:
        url = f"{self._base_url}/{method}"
        try:
            response = self._session.post(url, params=params, json=json_body, timeout=timeout)
        except requests.RequestException as exc:
            logger.error("Telegram request failed: method=%s error=%s", method, exc)
            raise TelegramAPIError(f"Telegram request failed: {method}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "Telegram returned invalid JSON: method=%s status=%s", method, response.status_code
            )
            raise TelegramAPIError(f"Telegram returned invalid JSON: {method}") from exc

        if not response.ok or not data.get("ok", False):
            logger.error("Telegram API error: method=%s status=%s", method, response.status_code)
            raise TelegramAPIError(f"Telegram API error: {method}")

        return data
