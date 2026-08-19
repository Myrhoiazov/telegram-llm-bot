"""Ollama HTTP provider implementing the TextGenerator contract."""
from __future__ import annotations

import logging

import requests

from app.inference.base import InferenceError

logger = logging.getLogger(__name__)


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self._url = f"{base_url}/api/generate"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def generate(self, prompt: str) -> str:
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        try:
            response = self._session.post(self._url, json=payload, timeout=self._timeout_seconds)
        except requests.RequestException as exc:
            logger.error("Ollama request failed: %s", exc)
            raise InferenceError("Ollama request failed") from exc

        if not response.ok:
            logger.error("Ollama returned error status: %s", response.status_code)
            raise InferenceError(f"Ollama returned status {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Ollama returned invalid JSON")
            raise InferenceError("Ollama returned invalid JSON") from exc

        text = data.get("response", "")
        if not isinstance(text, str) or not text.strip():
            logger.error("Ollama returned an empty response")
            raise InferenceError("Ollama returned an empty response")

        return text.strip()
