"""Ollama /api/chat client supporting native tool-calling."""
from __future__ import annotations

import json
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
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


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

        return _parse_message(data, message)


def _parse_arguments(raw: object) -> dict:
    """Tool-call arguments come back as an object, but some models/versions send a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            logger.warning("Ollama chat returned unparsable tool-call arguments")
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_message(data: dict, message: dict) -> ChatMessage:
    role = message.get("role", "assistant")
    content = message.get("content") or ""
    raw_tool_calls = message.get("tool_calls") or []
    tool_calls = tuple(
        ToolCall(
            id=call.get("id") or f"call_{index}",
            name=call["function"]["name"],
            arguments=_parse_arguments(call["function"].get("arguments")),
        )
        for index, call in enumerate(raw_tool_calls)
        if isinstance(call, dict) and isinstance(call.get("function"), dict) and "name" in call["function"]
    )
    prompt_tokens = data.get("prompt_eval_count")
    completion_tokens = data.get("eval_count")
    return ChatMessage(
        role=role,
        content=content,
        tool_calls=tool_calls,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
    )
