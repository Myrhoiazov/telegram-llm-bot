"""The agentic harness: loops the model through tool calls until a final answer or max-steps."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.inference.base import InferenceError
from app.memory.store import ConversationStore
from app.telemetry.events import (
    EVENT_AGENT_STEP_STARTED,
    EVENT_CONTEXT_LOADED,
    EVENT_FINAL_ANSWER,
    EVENT_LLM_COMPLETED,
    EVENT_LLM_STARTED,
    EVENT_TOOL_COMPLETED,
    EVENT_TOOL_REQUESTED,
    EVENT_TOOL_STARTED,
    TRACE_COMPLETED,
    TRACE_FAILED,
    TRACE_MAX_STEPS_REACHED,
)
from app.telemetry.tracer import NullTracer

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


@dataclass
class _RunCounters:
    agent_steps: int = 0
    llm_calls: int = 0
    tool_calls: int = 0


@dataclass
class _StepOutcome:
    text: str
    status: str
    error_type: str | None = None
    error_message: str | None = None


class AgentLoop:
    def __init__(
        self,
        chat_client,
        tool,
        store: ConversationStore,
        max_steps: int,
        max_context_messages: int,
        system_prompt: str,
        model: str = "",
        tracer=None,
    ) -> None:
        self._chat_client = chat_client
        self._tool = tool
        self._store = store
        self._max_steps = max_steps
        self._max_context_messages = max_context_messages
        self._system_prompt = system_prompt
        self._model = model
        self._tracer = tracer or NullTracer()

    def handle_message(self, chat_id: int, text: str) -> str:
        conversation_id = self._store.active_conversation_id(chat_id)
        trace_id = self._tracer.start_trace(chat_id, conversation_id, text, self._model)
        start = time.monotonic()

        self._store.append_message(conversation_id, "user", text)

        history = self._store.recent_messages(conversation_id, self._max_context_messages)
        self._tracer.emit(
            trace_id,
            EVENT_CONTEXT_LOADED,
            payload={"message_count": len(history), "max_context_messages": self._max_context_messages},
        )
        messages: list[dict] = [{"role": "system", "content": self._system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in history)

        tools = [self._tool.schema()]
        counters = _RunCounters()
        try:
            outcome = self._run_steps(trace_id, messages, tools, counters)
            duration_ms = int((time.monotonic() - start) * 1000)

            if outcome.status == TRACE_FAILED:
                self._tracer.fail_trace(
                    trace_id, outcome.error_type, outcome.error_message, duration_ms,
                    counters.agent_steps, counters.llm_calls, counters.tool_calls,
                )
            elif outcome.status == TRACE_MAX_STEPS_REACHED:
                self._tracer.max_steps_trace(
                    trace_id, self._max_steps, duration_ms,
                    counters.agent_steps, counters.llm_calls, counters.tool_calls,
                )
            else:
                self._tracer.emit(trace_id, EVENT_FINAL_ANSWER, payload={"content": outcome.text})
                self._tracer.complete_trace(
                    trace_id, duration_ms, counters.agent_steps, counters.llm_calls, counters.tool_calls
                )

            if outcome.text not in (FALLBACK_REPLY, MAX_STEPS_REPLY):
                self._store.append_message(conversation_id, "assistant", outcome.text)
            return outcome.text
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            self._tracer.fail_trace(
                trace_id, type(exc).__name__, str(exc), duration_ms,
                counters.agent_steps, counters.llm_calls, counters.tool_calls,
            )
            raise

    def _run_steps(self, trace_id: str, messages: list[dict], tools: list[dict], counters: _RunCounters) -> _StepOutcome:
        for step in range(1, self._max_steps + 1):
            counters.agent_steps = step
            self._tracer.emit(
                trace_id, EVENT_AGENT_STEP_STARTED, step=step, payload={"step": step, "max_steps": self._max_steps}
            )

            self._tracer.emit(
                trace_id, EVENT_LLM_STARTED, step=step,
                payload={"model": self._model, "message_count": len(messages)},
            )
            llm_start = time.monotonic()
            try:
                reply = self._chat_client.chat(messages, tools)
            except InferenceError as exc:
                logger.exception("Agent loop: chat call failed")
                return _StepOutcome(
                    text=FALLBACK_REPLY, status=TRACE_FAILED, error_type=type(exc).__name__, error_message=str(exc)
                )
            llm_duration_ms = int((time.monotonic() - llm_start) * 1000)
            counters.llm_calls += 1
            self._tracer.emit(
                trace_id, EVENT_LLM_COMPLETED, step=step, duration_ms=llm_duration_ms,
                payload={
                    "model": self._model,
                    "duration_ms": llm_duration_ms,
                    "prompt_tokens": reply.prompt_tokens,
                    "completion_tokens": reply.completion_tokens,
                },
            )

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
                    content = self._dispatch_tool(trace_id, step, call, counters)
                    messages.append({"role": "tool", "name": call.name, "content": content})
                continue

            if reply.content.strip():
                return _StepOutcome(text=reply.content.strip(), status=TRACE_COMPLETED)

            messages.append({"role": "user", "content": NUDGE_MESSAGE})

        return _StepOutcome(text=MAX_STEPS_REPLY, status=TRACE_MAX_STEPS_REACHED)

    def _dispatch_tool(self, trace_id: str, step: int, call, counters: _RunCounters) -> str:
        self._tracer.emit(
            trace_id, EVENT_TOOL_REQUESTED, step=step, payload={"tool": call.name, "arguments": call.arguments}
        )
        if call.name != self._tool.name:
            logger.warning("Agent loop: unknown tool requested: %s", call.name)
            return f"error: unknown tool '{call.name}'"

        command = call.arguments.get("command", "")
        self._tracer.emit(trace_id, EVENT_TOOL_STARTED, step=step, payload={"tool": call.name, "command": command})
        result = self._tool.run(command)
        counters.tool_calls += 1
        self._tracer.emit(
            trace_id, EVENT_TOOL_COMPLETED, step=step, duration_ms=result.duration_ms,
            payload={
                "tool": call.name,
                "command": command,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration_ms": result.duration_ms,
                "timed_out": result.timed_out,
                "truncated": result.truncated,
            },
        )
        return result.to_tool_content()
