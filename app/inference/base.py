"""Minimal, provider-agnostic text generation contract."""
from __future__ import annotations

from typing import Protocol


class TextGenerator(Protocol):
    def generate(self, prompt: str, system: str | None = None) -> str:
        ...


class InferenceError(Exception):
    """Raised when text generation fails for any reason."""
