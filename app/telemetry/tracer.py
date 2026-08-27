"""Trace lifecycle: creates traces, assigns sequence numbers, persists and broadcasts events."""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone

from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.events import (
    AgentEvent,
    EVENT_MAX_STEPS_REACHED,
    EVENT_TRACE_COMPLETED,
    EVENT_TRACE_FAILED,
    EVENT_TRACE_STARTED,
    TRACE_COMPLETED,
    TRACE_FAILED,
    TRACE_MAX_STEPS_REACHED,
    TRACE_RUNNING,
)
from app.telemetry.redact import redact_payload, redact_text
from app.telemetry.store import TraceStore

logger = logging.getLogger(__name__)


class AgentTracer:
    def __init__(self, store: TraceStore, broadcaster: EventBroadcaster, secrets: list[str] | None = None) -> None:
        self._store = store
        self._broadcaster = broadcaster
        self._secrets = [s for s in (secrets or []) if s]
        self._sequences: dict[str, int] = {}
        self._lock = threading.Lock()

    def start_trace(self, chat_id: int, conversation_id: int, user_message: str, model: str) -> str:
        trace_id = str(uuid.uuid4())
        with self._lock:
            self._sequences[trace_id] = 0
        try:
            self._store.create_trace(
                trace_id=trace_id,
                chat_id=chat_id,
                conversation_id=conversation_id,
                user_message=redact_text(user_message, self._secrets),
                status=TRACE_RUNNING,
                model=model,
                started_at=datetime.now(timezone.utc),
            )
        except Exception:
            logger.exception("telemetry: failed to create trace %s", trace_id)
        self.emit(
            trace_id,
            EVENT_TRACE_STARTED,
            payload={"chat_id": chat_id, "conversation_id": conversation_id, "user_message": user_message},
        )
        return trace_id

    def emit(
        self,
        trace_id: str,
        event_type: str,
        step: int | None = None,
        duration_ms: int | None = None,
        payload: dict | None = None,
    ) -> None:
        try:
            with self._lock:
                sequence = self._sequences.get(trace_id, 0)
                self._sequences[trace_id] = sequence + 1
            event = AgentEvent(
                trace_id=trace_id,
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                sequence=sequence,
                step=step,
                duration_ms=duration_ms,
                payload=redact_payload(payload or {}, self._secrets),
            )
            self._store.append_event(event)
            self._broadcaster.publish(event.to_dict())
        except Exception:
            logger.exception("telemetry: failed to emit event %s for trace %s", event_type, trace_id)

    def complete_trace(self, trace_id: str, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int) -> None:
        self.emit(
            trace_id,
            EVENT_TRACE_COMPLETED,
            duration_ms=duration_ms,
            payload={"duration_ms": duration_ms, "agent_steps": agent_steps, "llm_calls": llm_calls, "tool_calls": tool_calls},
        )
        self._finish(trace_id, TRACE_COMPLETED, duration_ms, agent_steps, llm_calls, tool_calls, error=None)

    def fail_trace(
        self, trace_id: str, error_type: str, message: str, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int
    ) -> None:
        self.emit(
            trace_id,
            EVENT_TRACE_FAILED,
            duration_ms=duration_ms,
            payload={"error_type": error_type, "message": message},
        )
        self._finish(
            trace_id, TRACE_FAILED, duration_ms, agent_steps, llm_calls, tool_calls,
            error=redact_text(f"{error_type}: {message}", self._secrets),
        )

    def max_steps_trace(
        self, trace_id: str, max_steps: int, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int
    ) -> None:
        self.emit(trace_id, EVENT_MAX_STEPS_REACHED, duration_ms=duration_ms, payload={"max_steps": max_steps})
        self._finish(trace_id, TRACE_MAX_STEPS_REACHED, duration_ms, agent_steps, llm_calls, tool_calls, error=None)

    def _finish(
        self,
        trace_id: str,
        status: str,
        duration_ms: int,
        agent_steps: int,
        llm_calls: int,
        tool_calls: int,
        error: str | None,
    ) -> None:
        try:
            self._store.update_trace_status(
                trace_id=trace_id,
                status=status,
                completed_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                agent_steps=agent_steps,
                llm_calls=llm_calls,
                tool_calls=tool_calls,
                error=error,
            )
        except Exception:
            logger.exception("telemetry: failed to finalize trace %s", trace_id)
        finally:
            with self._lock:
                self._sequences.pop(trace_id, None)


class NullTracer:
    def start_trace(self, chat_id: int, conversation_id: int, user_message: str, model: str) -> str:
        return ""

    def emit(
        self,
        trace_id: str,
        event_type: str,
        step: int | None = None,
        duration_ms: int | None = None,
        payload: dict | None = None,
    ) -> None:
        return None

    def complete_trace(self, trace_id: str, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int) -> None:
        return None

    def fail_trace(
        self, trace_id: str, error_type: str, message: str, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int
    ) -> None:
        return None

    def max_steps_trace(
        self, trace_id: str, max_steps: int, duration_ms: int, agent_steps: int, llm_calls: int, tool_calls: int
    ) -> None:
        return None
