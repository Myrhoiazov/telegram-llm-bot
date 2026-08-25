"""Ollama /api/chat client supporting native tool-calling."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from app.inference.base import InferenceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    tool_calls: tuple[ToolCall, ...] = ()


class OllamaChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self._url = f"{base_url}/api/chat"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def chat(self, messages: list[dict], tools: list[dict]) -> ChatMessage:
        payload = {"model": self._model, "messages": messages, "tools": tools, "stream": False}
        try:
            response = self._session.post(self._url, json=payload, timeout=self._timeout_seconds)
        except requests.RequestException as exc:
            logger.error("Ollama chat request failed: %s", exc)
            raise InferenceError("Ollama chat request failed") from exc

        if not response.ok:
            logger.error("Ollama chat returned error status: %s", response.status_code)
            raise InferenceError(f"Ollama chat returned status {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Ollama chat returned invalid JSON")
            raise InferenceError("Ollama chat returned invalid JSON") from exc

        message = data.get("message")
        if not isinstance(message, dict):
            logger.error("Ollama chat response missing message")
            raise InferenceError("Ollama chat response missing message")

        return _parse_message(message)


def _parse_message(message: dict) -> ChatMessage:
    role = message.get("role", "assistant")
    content = message.get("content") or ""
    raw_tool_calls = message.get("tool_calls") or []
    tool_calls = tuple(
        ToolCall(
            id=call.get("id") or f"call_{index}",
            name=call["function"]["name"],
            arguments=call["function"].get("arguments") or {},
        )
        for index, call in enumerate(raw_tool_calls)
        if isinstance(call, dict) and isinstance(call.get("function"), dict) and "name" in call["function"]
    )
    return ChatMessage(role=role, content=content, tool_calls=tool_calls)
