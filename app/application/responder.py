"""Simple responder abstraction backed by a TextGenerator."""
from __future__ import annotations

from typing import Protocol

from app.inference.base import TextGenerator


class Responder(Protocol):
    def respond(self, text: str) -> str:
        ...


class LLMResponder:
    """Stateless responder. Not an autonomous agent: no loop, tools, or memory."""

    def __init__(self, generator: TextGenerator) -> None:
        self._generator = generator

    def respond(self, text: str) -> str:
        return self._generator.generate(text)
