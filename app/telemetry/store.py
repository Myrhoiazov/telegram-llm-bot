"""SQLite persistence for agent traces and their events."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from app.telemetry.events import AgentEvent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT UNIQUE NOT NULL,
    chat_id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    user_message TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,
    agent_steps INTEGER NOT NULL DEFAULT 0,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS agent_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    step INTEGER,
    timestamp TEXT NOT NULL,
    duration_ms INTEGER,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_events_trace_sequence ON agent_events(trace_id, sequence);
"""


class TraceStore:
    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # WAL mode persists on the database file itself, so this also protects
            # ConversationStore (same file) from reader/writer lock contention.
            conn.execute("PRAGMA journal_mode=WAL")
            # Only one bot process ever writes traces to this file, so any trace still
            # marked RUNNING at startup was orphaned by a prior crash/restart, not a
            # concurrent writer. Resolve it so the dashboard's "active traces" count
            # doesn't inflate forever.
            conn.execute(
                "UPDATE agent_traces SET status = 'FAILED', "
                "error = 'interrupted: process restarted' WHERE status = 'RUNNING'"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_trace(
        self,
        trace_id: str,
        chat_id: int,
        conversation_id: int,
        user_message: str,
        status: str,
        model: str,
        started_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_traces
                    (trace_id, chat_id, conversation_id, user_message, status, model, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (trace_id, chat_id, conversation_id, user_message, status, model, started_at.isoformat()),
            )

    def append_event(self, event: AgentEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_events
                    (trace_id, sequence, event_type, step, timestamp, duration_ms, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.trace_id,
                    event.sequence,
                    event.event_type,
                    event.step,
                    event.timestamp.isoformat(),
                    event.duration_ms,
                    json.dumps(event.payload),
                ),
            )

    def update_trace_status(
        self,
        trace_id: str,
        status: str,
        completed_at: datetime,
        duration_ms: int,
        agent_steps: int,
        llm_calls: int,
        tool_calls: int,
        error: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE agent_traces
                SET status = ?, completed_at = ?, duration_ms = ?, agent_steps = ?,
                    llm_calls = ?, tool_calls = ?, error = ?
                WHERE trace_id = ?
                """,
                (status, completed_at.isoformat(), duration_ms, agent_steps, llm_calls, tool_calls, error, trace_id),
            )

    def get_trace(self, trace_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_traces WHERE trace_id = ?", (trace_id,)).fetchone()
        return dict(row) if row else None

    def get_events(self, trace_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_events WHERE trace_id = ? ORDER BY sequence ASC", (trace_id,)
            ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            event["payload"] = json.loads(event.pop("payload_json"))
            events.append(event)
        return events

    def list_traces(self, limit: int = 50, status: str | None = None, chat_id: int | None = None) -> list[dict]:
        query = "SELECT * FROM agent_traces WHERE 1=1"
        params: list = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if chat_id is not None:
            query += " AND chat_id = ?"
            params.append(chat_id)
        query += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_traces,
                    SUM(CASE WHEN status = 'RUNNING' THEN 1 ELSE 0 END) AS running,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status = 'MAX_STEPS_REACHED' THEN 1 ELSE 0 END) AS max_steps_reached,
                    AVG(duration_ms) AS average_duration_ms,
                    SUM(llm_calls) AS total_llm_calls,
                    SUM(tool_calls) AS total_tool_calls
                FROM agent_traces
                """
            ).fetchone()
        average = row["average_duration_ms"]
        return {
            "total_traces": row["total_traces"] or 0,
            "running": row["running"] or 0,
            "completed": row["completed"] or 0,
            "failed": row["failed"] or 0,
            "max_steps_reached": row["max_steps_reached"] or 0,
            "average_duration_ms": round(average) if average is not None else None,
            "total_llm_calls": row["total_llm_calls"] or 0,
            "total_tool_calls": row["total_tool_calls"] or 0,
        }
