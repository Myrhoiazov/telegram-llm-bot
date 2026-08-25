"""The agentic harness: loops the model through tool calls until a final answer or max-steps."""
from __future__ import annotations

import logging

from app.inference.base import InferenceError
from app.memory.store import ConversationStore

logger = logging.getLogger(__name__)

FALLBACK_REPLY = (
    "Сейчас не получилось получить ответ от локальной модели. "
    "Попробуйте еще раз чуть позже."
)
MAX_STEPS_REPLY = (
    "Не удалось завершить обработку запроса за отведённое число шагов. "
    "Попробуйте переформулировать вопрос."
)
NUDGE_MESSAGE = "Дай финальный ответ пользователю или вызови execute_command, если тебе нужно больше информации."


class AgentLoop:
    def __init__(
        self,
        chat_client,
        tool,
        store: ConversationStore,
        max_steps: int,
        max_context_messages: int,
        system_prompt: str,
    ) -> None:
        self._chat_client = chat_client
        self._tool = tool
        self._store = store
        self._max_steps = max_steps
        self._max_context_messages = max_context_messages
        self._system_prompt = system_prompt

    def handle_message(self, chat_id: int, text: str) -> str:
        conversation_id = self._store.active_conversation_id(chat_id)
        self._store.append_message(conversation_id, "user", text)

        history = self._store.recent_messages(conversation_id, self._max_context_messages)
        messages: list[dict] = [{"role": "system", "content": self._system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in history)

        tools = [self._tool.schema()]
        final_text = self._run_steps(messages, tools)

        self._store.append_message(conversation_id, "assistant", final_text)
        return final_text

    def _run_steps(self, messages: list[dict], tools: list[dict]) -> str:
        for _ in range(self._max_steps):
            try:
                reply = self._chat_client.chat(messages, tools)
            except InferenceError:
                logger.exception("Agent loop: chat call failed")
                return FALLBACK_REPLY

            if reply.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": reply.content,
                        "tool_calls": [
                            {"id": call.id, "function": {"name": call.name, "arguments": call.arguments}}
                            for call in reply.tool_calls
                        ],
                    }
                )
                for call in reply.tool_calls:
                    messages.append({"role": "tool", "name": call.name, "content": self._dispatch_tool(call)})
                continue

            if reply.content.strip():
                return reply.content.strip()

            messages.append({"role": "user", "content": NUDGE_MESSAGE})

        return MAX_STEPS_REPLY

    def _dispatch_tool(self, call) -> str:
        if call.name != self._tool.name:
            logger.warning("Agent loop: unknown tool requested: %s", call.name)
            return f"error: unknown tool '{call.name}'"
        command = call.arguments.get("command", "")
        result = self._tool.run(command)
        return result.to_tool_content()
