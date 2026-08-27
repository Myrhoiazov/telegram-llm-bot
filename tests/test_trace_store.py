from datetime import datetime, timezone

from app.telemetry.events import AgentEvent
from app.telemetry.store import TraceStore


def make_store(tmp_path):
    return TraceStore(str(tmp_path / "trace.sqlite3"))


def test_create_and_get_trace(tmp_path):
    store = make_store(tmp_path)
    started_at = datetime.now(timezone.utc)

    store.create_trace(
        trace_id="t1", chat_id=1, conversation_id=2, user_message="hi",
        status="RUNNING", model="qwen3:4b", started_at=started_at,
    )
    trace = store.get_trace("t1")

    assert trace["trace_id"] == "t1"
    assert trace["chat_id"] == 1
    assert trace["conversation_id"] == 2
    assert trace["user_message"] == "hi"
    assert trace["status"] == "RUNNING"
    assert trace["model"] == "qwen3:4b"
    assert trace["completed_at"] is None
    assert trace["agent_steps"] == 0


def test_get_trace_returns_none_for_unknown_id(tmp_path):
    store = make_store(tmp_path)

    assert store.get_trace("missing") is None


def test_append_event_and_get_events_ordered_by_sequence(tmp_path):
    store = make_store(tmp_path)
    store.create_trace(
        trace_id="t1", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
    )
    now = datetime.now(timezone.utc)
    store.append_event(AgentEvent(trace_id="t1", event_type="trace_started", timestamp=now, sequence=0, payload={"a": 1}))
    store.append_event(AgentEvent(trace_id="t1", event_type="final_answer", timestamp=now, sequence=1, payload={"content": "hi"}))

    events = store.get_events("t1")

    assert [e["event_type"] for e in events] == ["trace_started", "final_answer"]
    assert [e["sequence"] for e in events] == [0, 1]
    assert events[1]["payload"] == {"content": "hi"}


def test_update_trace_status_sets_completion_fields(tmp_path):
    store = make_store(tmp_path)
    store.create_trace(
        trace_id="t1", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
    )

    store.update_trace_status(
        trace_id="t1", status="COMPLETED", completed_at=datetime.now(timezone.utc),
        duration_ms=120, agent_steps=2, llm_calls=2, tool_calls=1, error=None,
    )
    trace = store.get_trace("t1")

    assert trace["status"] == "COMPLETED"
    assert trace["duration_ms"] == 120
    assert trace["agent_steps"] == 2
    assert trace["llm_calls"] == 2
    assert trace["tool_calls"] == 1
    assert trace["error"] is None
    assert trace["completed_at"] is not None


def test_list_traces_filters_by_status_and_chat_id(tmp_path):
    store = make_store(tmp_path)
    now = datetime.now(timezone.utc)
    store.create_trace(trace_id="t1", chat_id=1, conversation_id=1, user_message="a", status="RUNNING", model="m", started_at=now)
    store.create_trace(trace_id="t2", chat_id=1, conversation_id=1, user_message="b", status="COMPLETED", model="m", started_at=now)
    store.create_trace(trace_id="t3", chat_id=2, conversation_id=1, user_message="c", status="COMPLETED", model="m", started_at=now)

    completed_for_chat_1 = store.list_traces(status="COMPLETED", chat_id=1)

    assert [t["trace_id"] for t in completed_for_chat_1] == ["t2"]


def test_list_traces_respects_limit_and_orders_newest_first(tmp_path):
    store = make_store(tmp_path)
    for i in range(3):
        store.create_trace(
            trace_id=f"t{i}", chat_id=1, conversation_id=1, user_message="x",
            status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
        )

    traces = store.list_traces(limit=2)

    assert len(traces) == 2
    assert traces[0]["trace_id"] == "t2"


def test_get_stats_on_empty_store(tmp_path):
    store = make_store(tmp_path)

    stats = store.get_stats()

    assert stats == {
        "total_traces": 0, "running": 0, "completed": 0, "failed": 0,
        "max_steps_reached": 0, "average_duration_ms": None,
        "total_llm_calls": 0, "total_tool_calls": 0,
    }


def test_reopening_store_marks_stale_running_traces_failed(tmp_path):
    """Regression for final-branch-review finding #2: a trace still RUNNING when the process is killed
    (container restart) previously stayed RUNNING forever, permanently inflating the dashboard's active
    count. TraceStore now reconciles any orphaned RUNNING trace to FAILED at startup, since only one bot
    process ever writes to this file."""
    db_path = str(tmp_path / "trace.sqlite3")
    first_process_store = TraceStore(db_path)
    first_process_store.create_trace(
        trace_id="orphaned", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
    )

    # Simulate the process restarting and reopening the same database file.
    second_process_store = TraceStore(db_path)

    trace = second_process_store.get_trace("orphaned")
    assert trace["status"] == "FAILED"
    assert trace["error"] == "interrupted: process restarted"


def test_reopening_store_does_not_touch_terminal_traces(tmp_path):
    db_path = str(tmp_path / "trace.sqlite3")
    store = TraceStore(db_path)
    store.create_trace(
        trace_id="done", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
    )
    store.update_trace_status(
        trace_id="done", status="COMPLETED", completed_at=datetime.now(timezone.utc),
        duration_ms=10, agent_steps=1, llm_calls=1, tool_calls=0, error=None,
    )

    reopened_store = TraceStore(db_path)

    trace = reopened_store.get_trace("done")
    assert trace["status"] == "COMPLETED"
    assert trace["error"] is None


def test_trace_store_enables_wal_journal_mode(tmp_path):
    """Regression for final-branch-review finding #5: WAL mode lets dashboard reader threads coexist with
    the bot's own writer thread (ConversationStore, same file) without lock contention that could break a
    real Telegram reply."""
    store = TraceStore(str(tmp_path / "trace.sqlite3"))

    with store._connect() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode.lower() == "wal"


def test_get_stats_aggregates_across_traces(tmp_path):
    store = make_store(tmp_path)
    now = datetime.now(timezone.utc)
    store.create_trace(trace_id="t1", chat_id=1, conversation_id=1, user_message="a", status="RUNNING", model="m", started_at=now)
    store.update_trace_status(trace_id="t1", status="COMPLETED", completed_at=now, duration_ms=100, agent_steps=1, llm_calls=1, tool_calls=0, error=None)
    store.create_trace(trace_id="t2", chat_id=1, conversation_id=1, user_message="b", status="RUNNING", model="m", started_at=now)
    store.update_trace_status(trace_id="t2", status="FAILED", completed_at=now, duration_ms=200, agent_steps=1, llm_calls=1, tool_calls=1, error="boom")

    stats = store.get_stats()

    assert stats["total_traces"] == 2
    assert stats["completed"] == 1
    assert stats["failed"] == 1
    assert stats["average_duration_ms"] == 150
    assert stats["total_llm_calls"] == 2
    assert stats["total_tool_calls"] == 1
