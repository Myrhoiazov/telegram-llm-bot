"""Simple responder abstraction backed by a TextGenerator."""
from __future__ import annotations

from typing import Protocol

from app.inference.base import TextGenerator


class Responder(Protocol):
    def respond(self, text: str) -> str:
        ...


SYSTEM_PROMPT = """<role>
Ты — ассистент Telegram-бота.
</role>

<rules>
<rule>Отвечай только проверенными фактами, без домыслов и предположений.</rule>
<rule>Если не уверен в ответе или не знаешь его точно, прямо напиши: "Я не знаю точного ответа на этот вопрос".</rule>
<rule>Никогда не придумывай правдоподобные, но непроверенные детали.</rule>
<rule>Отвечай кратко и по делу, без лишних вступлений.</rule>
<rule>Отвечай на русском языке.</rule>
</rules>"""


class LLMResponder:
    """Stateless responder. Not an autonomous agent: no loop, tools, or memory."""

    def __init__(self, generator: TextGenerator) -> None:
        self._generator = generator

    def respond(self, text: str) -> str:
        return self._generator.generate(text, system=SYSTEM_PROMPT)
