"""Event and status constants plus the AgentEvent record shared by the tracer, store, and dashboard."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

TRACE_RUNNING = "RUNNING"
TRACE_COMPLETED = "COMPLETED"
TRACE_FAILED = "FAILED"
TRACE_MAX_STEPS_REACHED = "MAX_STEPS_REACHED"

TRACE_STATUSES = frozenset({TRACE_RUNNING, TRACE_COMPLETED, TRACE_FAILED, TRACE_MAX_STEPS_REACHED})

EVENT_TRACE_STARTED = "trace_started"
EVENT_CONTEXT_LOADED = "context_loaded"
EVENT_AGENT_STEP_STARTED = "agent_step_started"
EVENT_LLM_STARTED = "llm_started"
EVENT_LLM_COMPLETED = "llm_completed"
EVENT_TOOL_REQUESTED = "tool_requested"
EVENT_TOOL_STARTED = "tool_started"
EVENT_TOOL_COMPLETED = "tool_completed"
EVENT_FINAL_ANSWER = "final_answer"
EVENT_TRACE_COMPLETED = "trace_completed"
EVENT_TRACE_FAILED = "trace_failed"
EVENT_MAX_STEPS_REACHED = "max_steps_reached"
EVENT_SKILL_ACCESSED = "skill_accessed"


@dataclass(frozen=True)
class AgentEvent:
    trace_id: str
    event_type: str
    timestamp: datetime
    sequence: int
    step: int | None = None
    duration_ms: int | None = None
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "sequence": self.sequence,
            "step": self.step,
            "duration_ms": self.duration_ms,
            "payload": self.payload,
        }
