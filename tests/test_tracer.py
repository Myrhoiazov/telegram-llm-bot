from app.telemetry.redact import redact_payload, redact_text


def test_redact_text_replaces_known_secret():
    assert redact_text("token is abc123 in the log", ["abc123"]) == "token is *** in the log"


def test_redact_text_ignores_empty_secret_list():
    assert redact_text("nothing secret here", []) == "nothing secret here"


def test_redact_payload_redacts_nested_strings():
    payload = {
        "command": "curl -H 'Authorization: abc123' https://example.com",
        "arguments": {"password": "abc123"},
        "list": ["abc123", "safe"],
        "count": 3,
    }

    redacted = redact_payload(payload, ["abc123"])

    assert redacted["command"] == "curl -H 'Authorization: ***' https://example.com"
    assert redacted["arguments"]["password"] == "***"
    assert redacted["list"] == ["***", "safe"]
    assert redacted["count"] == 3


def test_redact_text_handles_overlapping_substring_secrets():
    """Regression: longer secrets must be redacted before their substrings.
    If ["abc", "abc123xyz"] is given and "abc" is processed first,
    the text "abc123xyz" becomes "***123xyz", so "abc123xyz" no longer matches.
    Sorting by descending length prevents this leakage."""
    # Note: secrets list order is ["abc", "abc123xyz"] — shorter first
    result = redact_text("token abc123xyz in log", ["abc", "abc123xyz"])
    # Both should be fully redacted; no "123xyz" leakage
    assert result == "token *** in log"
    assert "123xyz" not in result


from datetime import datetime, timezone

from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.store import TraceStore
from app.telemetry.tracer import AgentTracer, NullTracer


def make_tracer(tmp_path, secrets=None):
    store = TraceStore(str(tmp_path / "trace.sqlite3"))
    broadcaster = EventBroadcaster()
    tracer = AgentTracer(store, broadcaster, secrets=secrets)
    return tracer, store, broadcaster


def test_broadcaster_delivers_published_event_to_subscriber():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()

    broadcaster.publish({"event_type": "trace_started"})

    assert q.get_nowait() == {"event_type": "trace_started"}


def test_broadcaster_does_not_deliver_to_unsubscribed_queue():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()
    broadcaster.unsubscribe(q)

    broadcaster.publish({"event_type": "trace_started"})

    assert q.empty()


def test_broadcaster_tracks_subscriber_count():
    broadcaster = EventBroadcaster()
    assert broadcaster.subscriber_count() == 0

    q = broadcaster.subscribe()
    assert broadcaster.subscriber_count() == 1

    broadcaster.unsubscribe(q)
    assert broadcaster.subscriber_count() == 0


def test_start_trace_persists_trace_and_emits_trace_started(tmp_path):
    tracer, store, broadcaster = make_tracer(tmp_path)
    subscriber = broadcaster.subscribe()

    trace_id = tracer.start_trace(chat_id=1, conversation_id=2, user_message="hi", model="qwen3:4b")

    trace = store.get_trace(trace_id)
    assert trace["chat_id"] == 1
    assert trace["status"] == "RUNNING"
    events = store.get_events(trace_id)
    assert events[0]["event_type"] == "trace_started"
    assert events[0]["sequence"] == 0
    published = subscriber.get_nowait()
    assert published["event_type"] == "trace_started"


def test_emit_assigns_incrementing_sequence(tmp_path):
    tracer, store, _ = make_tracer(tmp_path)
    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")

    tracer.emit(trace_id, "context_loaded", payload={"message_count": 1})
    tracer.emit(trace_id, "agent_step_started", step=1, payload={"step": 1, "max_steps": 8})

    events = store.get_events(trace_id)
    assert [e["sequence"] for e in events] == [0, 1, 2]
    assert [e["event_type"] for e in events] == ["trace_started", "context_loaded", "agent_step_started"]


def test_complete_trace_emits_event_and_updates_status(tmp_path):
    tracer, store, subscriber_store = make_tracer(tmp_path)
    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")

    tracer.complete_trace(trace_id, duration_ms=50, agent_steps=1, llm_calls=1, tool_calls=0)

    trace = store.get_trace(trace_id)
    assert trace["status"] == "COMPLETED"
    assert trace["duration_ms"] == 50
    events = store.get_events(trace_id)
    assert events[-1]["event_type"] == "trace_completed"


def test_fail_trace_emits_event_and_sets_error(tmp_path):
    tracer, store, _ = make_tracer(tmp_path)
    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")

    tracer.fail_trace(trace_id, error_type="InferenceError", message="boom", duration_ms=10, agent_steps=1, llm_calls=1, tool_calls=0)

    trace = store.get_trace(trace_id)
    assert trace["status"] == "FAILED"
    assert trace["error"] == "InferenceError: boom"
    events = store.get_events(trace_id)
    assert events[-1]["event_type"] == "trace_failed"


def test_max_steps_trace_emits_event_and_sets_status(tmp_path):
    tracer, store, _ = make_tracer(tmp_path)
    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")

    tracer.max_steps_trace(trace_id, max_steps=8, duration_ms=10, agent_steps=8, llm_calls=8, tool_calls=3)

    trace = store.get_trace(trace_id)
    assert trace["status"] == "MAX_STEPS_REACHED"
    events = store.get_events(trace_id)
    assert events[-1]["event_type"] == "max_steps_reached"
    assert events[-1]["payload"] == {"max_steps": 8}


def test_emit_redacts_known_secrets_in_payload(tmp_path):
    tracer, store, _ = make_tracer(tmp_path, secrets=["super-secret"])
    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")

    tracer.emit(trace_id, "tool_started", step=1, payload={"tool": "execute_command", "command": "echo super-secret"})

    events = store.get_events(trace_id)
    assert events[-1]["payload"]["command"] == "echo ***"


def test_start_trace_redacts_user_message_in_store(tmp_path):
    tracer, store, _ = make_tracer(tmp_path, secrets=["super-secret"])

    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="my token is super-secret", model="m")

    trace = store.get_trace(trace_id)
    assert trace["user_message"] == "my token is ***"


def test_tracer_swallows_store_failures(tmp_path):
    class BoomStore:
        def create_trace(self, *args, **kwargs):
            raise RuntimeError("disk full")

        def append_event(self, *args, **kwargs):
            raise RuntimeError("disk full")

    tracer = AgentTracer(BoomStore(), EventBroadcaster())

    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")
    tracer.emit(trace_id, "context_loaded", payload={})

    assert isinstance(trace_id, str)


def test_null_tracer_is_a_complete_no_op():
    tracer = NullTracer()

    trace_id = tracer.start_trace(chat_id=1, conversation_id=1, user_message="hi", model="m")
    tracer.emit(trace_id, "context_loaded", payload={})
    tracer.complete_trace(trace_id, duration_ms=1, agent_steps=1, llm_calls=1, tool_calls=0)
    tracer.fail_trace(trace_id, "Err", "msg", duration_ms=1, agent_steps=1, llm_calls=1, tool_calls=0)
    tracer.max_steps_trace(trace_id, max_steps=8, duration_ms=1, agent_steps=8, llm_calls=8, tool_calls=0)

    assert trace_id == ""
