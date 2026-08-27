import json
import threading
import time
from datetime import datetime, timezone

import pytest
import requests

from app.dashboard.server import build_dashboard_server
from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.events import AgentEvent
from app.telemetry.store import TraceStore


@pytest.fixture
def dashboard(tmp_path):
    store = TraceStore(str(tmp_path / "trace.sqlite3"))
    broadcaster = EventBroadcaster()
    # A short heartbeat matters even for tests that never assert on pings: ThreadingHTTPServer's
    # server_close() joins every handler thread it spawned, including one still blocked inside an
    # open SSE connection's queue.get(timeout=heartbeat_seconds) — at the default 20s heartbeat,
    # fixture teardown after any SSE test would block for up to 20s waiting for that join.
    server = build_dashboard_server("127.0.0.1", 0, store, broadcaster, max_list_limit=100, heartbeat_seconds=2.0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    yield base_url, store, broadcaster
    server.shutdown()
    server.server_close()


def test_index_serves_html(dashboard):
    base_url, _, _ = dashboard

    response = requests.get(f"{base_url}/", timeout=5)

    assert response.status_code == 200
    assert "text/html" in response.headers["Content-Type"]


def test_unknown_path_returns_404(dashboard):
    base_url, _, _ = dashboard

    response = requests.get(f"{base_url}/nope", timeout=5)

    assert response.status_code == 404


def test_get_stats_on_empty_store(dashboard):
    base_url, _, _ = dashboard

    response = requests.get(f"{base_url}/api/stats", timeout=5)

    assert response.status_code == 200
    assert response.json()["total_traces"] == 0


def test_list_traces_returns_created_trace(dashboard):
    base_url, store, _ = dashboard
    store.create_trace(
        trace_id="t1", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="qwen3:4b", started_at=datetime.now(timezone.utc),
    )

    response = requests.get(f"{base_url}/api/traces", timeout=5)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["trace_id"] == "t1"


def test_list_traces_filters_by_status(dashboard):
    base_url, store, _ = dashboard
    now = datetime.now(timezone.utc)
    store.create_trace(trace_id="t1", chat_id=1, conversation_id=1, user_message="a", status="RUNNING", model="m", started_at=now)
    store.create_trace(trace_id="t2", chat_id=1, conversation_id=1, user_message="b", status="COMPLETED", model="m", started_at=now)

    response = requests.get(f"{base_url}/api/traces", params={"status": "COMPLETED"}, timeout=5)

    body = response.json()
    assert [t["trace_id"] for t in body] == ["t2"]


def test_list_traces_clamps_limit_to_max_list_limit(dashboard):
    base_url, store, _ = dashboard
    for i in range(5):
        store.create_trace(
            trace_id=f"t{i}", chat_id=1, conversation_id=1, user_message="x",
            status="RUNNING", model="m", started_at=datetime.now(timezone.utc),
        )

    response = requests.get(f"{base_url}/api/traces", params={"limit": 100000}, timeout=5)

    assert response.status_code == 200
    assert len(response.json()) == 5


def test_get_trace_returns_404_for_unknown_id(dashboard):
    base_url, _, _ = dashboard

    response = requests.get(f"{base_url}/api/traces/missing", timeout=5)

    assert response.status_code == 404


def test_get_trace_returns_summary(dashboard):
    base_url, store, _ = dashboard
    store.create_trace(
        trace_id="t1", chat_id=1, conversation_id=1, user_message="hi",
        status="RUNNING", model="qwen3:4b", started_at=datetime.now(timezone.utc),
    )

    response = requests.get(f"{base_url}/api/traces/t1", timeout=5)

    assert response.status_code == 200
    assert response.json()["trace_id"] == "t1"


def test_get_trace_events_ordered_by_sequence(dashboard):
    base_url, store, _ = dashboard
    now = datetime.now(timezone.utc)
    store.create_trace(trace_id="t1", chat_id=1, conversation_id=1, user_message="hi", status="RUNNING", model="m", started_at=now)
    store.append_event(AgentEvent(trace_id="t1", event_type="trace_started", timestamp=now, sequence=0, payload={}))
    store.append_event(AgentEvent(trace_id="t1", event_type="final_answer", timestamp=now, sequence=1, payload={"content": "hi"}))

    response = requests.get(f"{base_url}/api/traces/t1/events", timeout=5)

    events = response.json()
    assert [e["event_type"] for e in events] == ["trace_started", "final_answer"]


def test_sse_stream_has_correct_content_type_and_delivers_event(dashboard):
    base_url, _, broadcaster = dashboard

    response = requests.get(f"{base_url}/api/events/stream", stream=True, timeout=5)
    assert response.headers["Content-Type"] == "text/event-stream"

    time.sleep(0.2)
    broadcaster.publish({"event_type": "trace_started", "trace_id": "t1"})

    lines = response.iter_lines(decode_unicode=True)
    collected = []
    for line in lines:
        if line:
            collected.append(line)
        if len(collected) >= 2:
            break
    response.close()

    assert collected[0] == "event: agent_event"
    assert json.loads(collected[1][len("data: "):])["trace_id"] == "t1"


def test_sse_stream_sends_heartbeat_ping_when_idle(tmp_path):
    store = TraceStore(str(tmp_path / "trace.sqlite3"))
    broadcaster = EventBroadcaster()
    server = build_dashboard_server("127.0.0.1", 0, store, broadcaster, max_list_limit=100, heartbeat_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    try:
        response = requests.get(f"http://127.0.0.1:{port}/api/events/stream", stream=True, timeout=5)
        lines = response.iter_lines(decode_unicode=True)
        collected = []
        for line in lines:
            if line:
                collected.append(line)
            if len(collected) >= 2:
                break
        response.close()
    finally:
        server.shutdown()
        server.server_close()

    assert collected[0] == "event: ping"
    assert collected[1] == "data: {}"


def test_sse_stream_disconnect_unsubscribes_without_crashing_server(tmp_path):
    store = TraceStore(str(tmp_path / "trace.sqlite3"))
    broadcaster = EventBroadcaster()
    # A short heartbeat is essential here: the handler only notices a closed socket the next
    # time it tries to write to it, which happens at most once per heartbeat interval.
    server = build_dashboard_server("127.0.0.1", 0, store, broadcaster, max_list_limit=100, heartbeat_seconds=0.2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    try:
        response = requests.get(f"http://127.0.0.1:{port}/api/events/stream", stream=True, timeout=5)
        time.sleep(0.1)
        assert broadcaster.subscriber_count() == 1

        response.close()
        time.sleep(0.5)

        assert broadcaster.subscriber_count() == 0
        health_check = requests.get(f"http://127.0.0.1:{port}/api/stats", timeout=5)
        assert health_check.status_code == 200
    finally:
        server.shutdown()
        server.server_close()
