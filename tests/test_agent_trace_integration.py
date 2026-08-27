from datetime import datetime, timezone

from app.agent.loop import AgentLoop, FALLBACK_REPLY, MAX_STEPS_REPLY
from app.inference.base import InferenceError
from app.inference.ollama_chat import ChatMessage, ToolCall
from app.memory.store import ConversationStore
from app.telemetry.broadcaster import EventBroadcaster
from app.telemetry.store import TraceStore
from app.telemetry.tracer import AgentTracer


class FakeChatClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def chat(self, messages, tools):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeExecResult:
    def __init__(self, text, exit_code=0, stdout="", stderr="", duration_ms=5, timed_out=False, truncated=False):
        self._text = text
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration_ms = duration_ms
        self.timed_out = timed_out
        self.truncated = truncated

    def to_tool_content(self):
        return self._text


class FakeTool:
    name = "execute_command"

    def __init__(self, result_text="exit_code=0\nstdout=ok\nstderr="):
        self._result_text = result_text

    def run(self, command):
        return FakeExecResult(self._result_text, stdout="ok")

    def schema(self):
        return {"type": "function", "function": {"name": self.name}}


def make_loop(tmp_path, chat_client, tool=None, max_steps=8):
    store = TraceStore(str(tmp_path / "trace.sqlite3"))
    tracer = AgentTracer(store, EventBroadcaster())
    loop = AgentLoop(
        chat_client=chat_client,
        tool=tool or FakeTool(),
        store=ConversationStore(":memory:"),
        max_steps=max_steps,
        max_context_messages=30,
        system_prompt="SYSTEM",
        model="qwen3:4b",
        tracer=tracer,
    )
    return loop, store


def test_final_answer_path_persists_expected_event_sequence(tmp_path):
    chat_client = FakeChatClient([ChatMessage(role="assistant", content="hello back")])
    loop, store = make_loop(tmp_path, chat_client)

    reply = loop.handle_message(chat_id=1, text="hi")

    traces = store.list_traces()
    assert len(traces) == 1
    trace = traces[0]
    assert trace["status"] == "COMPLETED"
    assert trace["llm_calls"] == 1
    assert trace["tool_calls"] == 0

    events = store.get_events(trace["trace_id"])
    assert [e["event_type"] for e in events] == [
        "trace_started", "context_loaded", "agent_step_started",
        "llm_started", "llm_completed", "final_answer", "trace_completed",
    ]
    assert [e["sequence"] for e in events] == list(range(len(events)))
    assert reply == "hello back"


def test_tool_path_persists_expected_event_sequence(tmp_path):
    chat_client = FakeChatClient(
        [
            ChatMessage(
                role="assistant", content="",
                tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
            ),
            ChatMessage(role="assistant", content="today is monday"),
        ]
    )
    loop, store = make_loop(tmp_path, chat_client)

    loop.handle_message(chat_id=1, text="what day is it")

    trace = store.list_traces()[0]
    events = store.get_events(trace["trace_id"])
    assert [e["event_type"] for e in events] == [
        "trace_started", "context_loaded", "agent_step_started", "llm_started", "llm_completed",
        "tool_requested", "tool_started", "tool_completed",
        "agent_step_started", "llm_started", "llm_completed", "final_answer", "trace_completed",
    ]


def test_ollama_failure_persists_failed_trace(tmp_path):
    chat_client = FakeChatClient([InferenceError("boom")])
    loop, store = make_loop(tmp_path, chat_client)

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == FALLBACK_REPLY
    trace = store.list_traces()[0]
    assert trace["status"] == "FAILED"
    assert trace["error"] == "InferenceError: boom"
    events = store.get_events(trace["trace_id"])
    assert events[-1]["event_type"] == "trace_failed"


def test_tool_timeout_persists_completed_trace_with_timed_out_flag(tmp_path):
    chat_client = FakeChatClient(
        [
            ChatMessage(
                role="assistant", content="",
                tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "sleep 999"}),),
            ),
            ChatMessage(role="assistant", content="that took too long"),
        ]
    )
    tool = FakeTool()
    tool.run = lambda command: FakeExecResult("timed_out=true exit_code=-1", exit_code=-1, timed_out=True, truncated=False)
    loop, store = make_loop(tmp_path, chat_client, tool=tool)

    loop.handle_message(chat_id=1, text="run something slow")

    trace = store.list_traces()[0]
    events = store.get_events(trace["trace_id"])
    tool_completed = next(e for e in events if e["event_type"] == "tool_completed")
    assert tool_completed["payload"]["timed_out"] is True


def test_max_steps_reached_persists_max_steps_status(tmp_path):
    looping_call = ChatMessage(
        role="assistant", content="",
        tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
    )
    chat_client = FakeChatClient([looping_call] * 2)
    loop, store = make_loop(tmp_path, chat_client, max_steps=2)

    reply = loop.handle_message(chat_id=1, text="loop forever")

    assert reply == MAX_STEPS_REPLY
    trace = store.list_traces()[0]
    assert trace["status"] == "MAX_STEPS_REACHED"
    events = store.get_events(trace["trace_id"])
    assert events[-1]["event_type"] == "max_steps_reached"
    assert events[-1]["payload"] == {"max_steps": 2}


def test_non_inference_exception_persists_failed_trace_and_propagates(tmp_path):
    """Regression for final-branch-review finding #1: previously only InferenceError was caught around the
    agent loop, so any other exception (bug, unexpected failure) left the trace row stuck RUNNING forever
    and leaked tracer sequence state. Now handle_message closes the trace via fail_trace on any exception
    before re-raising it."""
    chat_client = FakeChatClient([RuntimeError("boom from nowhere")])
    loop, store = make_loop(tmp_path, chat_client)

    try:
        loop.handle_message(chat_id=1, text="hi")
        assert False, "expected RuntimeError to propagate"
    except RuntimeError as exc:
        assert str(exc) == "boom from nowhere"

    trace = store.list_traces()[0]
    assert trace["status"] == "FAILED"
    assert trace["error"] == "RuntimeError: boom from nowhere"
    events = store.get_events(trace["trace_id"])
    assert events[-1]["event_type"] == "trace_failed"

    # Tracer's internal sequence-tracking state must be cleaned up too, exactly like the InferenceError
    # path: starting a fresh trace should resume sequence numbering from 0, not carry over.
    chat_client_2 = FakeChatClient([ChatMessage(role="assistant", content="ok")])
    loop._chat_client = chat_client_2
    loop.handle_message(chat_id=1, text="second message")
    second_trace = next(t for t in store.list_traces() if t["trace_id"] != trace["trace_id"])
    second_events = store.get_events(second_trace["trace_id"])
    assert second_events[0]["sequence"] == 0


def test_trace_store_failure_does_not_prevent_reply(tmp_path):
    class BoomStore(TraceStore):
        def append_event(self, event):
            raise RuntimeError("disk full")

    store = BoomStore(str(tmp_path / "trace.sqlite3"))
    tracer = AgentTracer(store, EventBroadcaster())
    chat_client = FakeChatClient([ChatMessage(role="assistant", content="hello back")])
    loop = AgentLoop(
        chat_client=chat_client, tool=FakeTool(), store=ConversationStore(":memory:"),
        max_steps=8, max_context_messages=30, system_prompt="SYSTEM", model="m", tracer=tracer,
    )

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == "hello back"
