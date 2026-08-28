"""Lemonade OpenAI-compatible speech-to-text client."""
from __future__ import annotations

from pathlib import Path

import requests


class TranscriptionError(Exception):
    """Raised when the STT provider fails or returns unusable text."""


class LemonadeTranscriber:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()

    def transcribe(self, wav_path: Path) -> str:
        try:
            with wav_path.open("rb") as audio:
                response = self._session.post(
                    f"{self._base_url}/v1/audio/transcriptions",
                    files={"file": audio},
                    data={"model": self._model},
                    timeout=self._timeout_seconds,
                )
        except OSError as exc:
            raise TranscriptionError("failed to read audio file") from exc
        except requests.RequestException as exc:
            raise TranscriptionError("STT request failed") from exc

        if not response.ok:
            raise TranscriptionError(f"STT provider returned HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError as exc:
            raise TranscriptionError("STT provider returned invalid JSON") from exc

        text = data.get("text")
        if not isinstance(text, str):
            raise TranscriptionError("STT provider returned invalid transcription")
        return text.strip()
