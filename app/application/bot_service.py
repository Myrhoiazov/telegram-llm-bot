"""Main use case: turn one incoming user message into one reply, via the agent loop."""
from __future__ import annotations


class BotService:
    def __init__(self, agent) -> None:
        self._agent = agent

    def handle_message(self, chat_id: int, text: str) -> str:
        return self._agent.handle_message(chat_id, text)
