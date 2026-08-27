import pytest

from app.agent.loop import FALLBACK_REPLY, MAX_STEPS_REPLY, AgentLoop
from app.inference.base import InferenceError
from app.inference.ollama_chat import ChatMessage, ToolCall
from app.memory.store import ConversationStore


class FakeChatClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat(self, messages, tools):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
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


class FakeTracer:
    def __init__(self):
        self.calls = []

    def start_trace(self, chat_id, conversation_id, user_message, model):
        self.calls.append(("start_trace", {"chat_id": chat_id, "conversation_id": conversation_id, "user_message": user_message, "model": model}))
        return "trace-1"

    def emit(self, trace_id, event_type, step=None, duration_ms=None, payload=None):
        self.calls.append(("emit", event_type, {"trace_id": trace_id, "step": step, "duration_ms": duration_ms, "payload": payload or {}}))

    def complete_trace(self, trace_id, duration_ms, agent_steps, llm_calls, tool_calls):
        self.calls.append(("complete_trace", {"trace_id": trace_id, "agent_steps": agent_steps, "llm_calls": llm_calls, "tool_calls": tool_calls}))

    def fail_trace(self, trace_id, error_type, message, duration_ms, agent_steps, llm_calls, tool_calls):
        self.calls.append(("fail_trace", {"trace_id": trace_id, "error_type": error_type, "message": message}))

    def max_steps_trace(self, trace_id, max_steps, duration_ms, agent_steps, llm_calls, tool_calls):
        self.calls.append(("max_steps_trace", {"trace_id": trace_id, "max_steps": max_steps}))

    def event_types(self):
        return [call[1] for call in self.calls if call[0] == "emit"]


class FakeTool:
    name = "execute_command"

    def __init__(self, result_text="exit_code=0\nstdout=ok\nstderr="):
        self._result_text = result_text
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        return FakeExecResult(self._result_text)

    def schema(self):
        return {"type": "function", "function": {"name": self.name}}


def make_loop(chat_client, tool=None, store=None, max_steps=8, max_context_messages=30, model="test-model", tracer=None):
    return AgentLoop(
        chat_client=chat_client,
        tool=tool or FakeTool(),
        store=store or ConversationStore(":memory:"),
        max_steps=max_steps,
        max_context_messages=max_context_messages,
        system_prompt="SYSTEM",
        model=model,
        tracer=tracer,
    )


def test_returns_final_answer_without_tool_call():
    chat_client = FakeChatClient([ChatMessage(role="assistant", content="hello back")])
    loop = make_loop(chat_client)

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == "hello back"
    assert chat_client.calls[0]["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert chat_client.calls[0]["messages"][-1] == {"role": "user", "content": "hi"}


def test_executes_tool_then_returns_final_answer():
    chat_client = FakeChatClient(
        [
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
            ),
            ChatMessage(role="assistant", content="today is monday"),
        ]
    )
    tool = FakeTool(result_text="exit_code=0\nstdout=Monday\nstderr=")
    loop = make_loop(chat_client, tool=tool)

    reply = loop.handle_message(chat_id=1, text="what day is it")

    assert reply == "today is monday"
    assert tool.commands == ["date"]
    second_call_messages = chat_client.calls[1]["messages"]
    assert second_call_messages[-1] == {
        "role": "tool",
        "name": "execute_command",
        "content": "exit_code=0\nstdout=Monday\nstderr=",
    }


def test_stops_after_max_steps_and_returns_fallback():
    looping_call = ChatMessage(
        role="assistant",
        content="",
        tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
    )
    chat_client = FakeChatClient([looping_call] * 3)
    loop = make_loop(chat_client, max_steps=3)

    reply = loop.handle_message(chat_id=1, text="loop forever")

    assert reply == MAX_STEPS_REPLY
    assert len(chat_client.calls) == 3


def test_nudges_on_empty_response_without_tool_call():
    chat_client = FakeChatClient(
        [
            ChatMessage(role="assistant", content=""),
            ChatMessage(role="assistant", content="final answer"),
        ]
    )
    loop = make_loop(chat_client)

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == "final answer"
    assert len(chat_client.calls) == 2
    assert chat_client.calls[1]["messages"][-1]["role"] == "user"


def test_returns_fallback_on_inference_error():
    chat_client = FakeChatClient([InferenceError("boom")])
    loop = make_loop(chat_client)

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == FALLBACK_REPLY


def test_fallback_reply_is_not_persisted_to_store():
    chat_client = FakeChatClient([InferenceError("boom")])
    store = ConversationStore(":memory:")
    loop = make_loop(chat_client, store=store)

    loop.handle_message(chat_id=1, text="hi")

    conversation_id = store.active_conversation_id(chat_id=1)
    stored = store.recent_messages(conversation_id, limit=10)
    assert [(m.role, m.content) for m in stored] == [("user", "hi")]


def test_max_steps_reply_is_not_persisted_to_store():
    looping_call = ChatMessage(
        role="assistant",
        content="",
        tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
    )
    chat_client = FakeChatClient([looping_call] * 3)
    store = ConversationStore(":memory:")
    loop = make_loop(chat_client, store=store, max_steps=3)

    loop.handle_message(chat_id=1, text="loop forever")

    conversation_id = store.active_conversation_id(chat_id=1)
    stored = store.recent_messages(conversation_id, limit=10)
    assert [(m.role, m.content) for m in stored] == [("user", "loop forever")]


def test_persists_only_user_message_and_final_answer():
    chat_client = FakeChatClient(
        [
            ChatMessage(
                role="assistant",
                content="",
                tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
            ),
            ChatMessage(role="assistant", content="today is monday"),
        ]
    )
    store = ConversationStore(":memory:")
    loop = make_loop(chat_client, store=store)

    loop.handle_message(chat_id=1, text="what day is it")

    conversation_id = store.active_conversation_id(chat_id=1)
    stored = store.recent_messages(conversation_id, limit=10)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "what day is it"),
        ("assistant", "today is monday"),
    ]


def test_second_turn_includes_trimmed_history():
    chat_client = FakeChatClient(
        [
            ChatMessage(role="assistant", content="first reply"),
            ChatMessage(role="assistant", content="second reply"),
        ]
    )
    loop = make_loop(chat_client, max_context_messages=30)

    loop.handle_message(chat_id=1, text="first message")
    loop.handle_message(chat_id=1, text="second message")

    second_turn_messages = chat_client.calls[1]["messages"]
    assert second_turn_messages == [
        {"role": "system", "content": "SYSTEM"},
        {"role": "user", "content": "first message"},
        {"role": "assistant", "content": "first reply"},
        {"role": "user", "content": "second message"},
    ]


def test_emits_full_event_sequence_for_final_answer():
    chat_client = FakeChatClient([ChatMessage(role="assistant", content="hello back")])
    tracer = FakeTracer()
    loop = make_loop(chat_client, tracer=tracer)

    loop.handle_message(chat_id=1, text="hi")

    assert tracer.event_types() == [
        "context_loaded", "agent_step_started", "llm_started", "llm_completed", "final_answer",
    ]
    assert tracer.calls[0] == ("start_trace", {"chat_id": 1, "conversation_id": 1, "user_message": "hi", "model": "test-model"})
    assert tracer.calls[-1][0] == "complete_trace"
    assert tracer.calls[-1][1]["agent_steps"] == 1
    assert tracer.calls[-1][1]["llm_calls"] == 1
    assert tracer.calls[-1][1]["tool_calls"] == 0


def test_emits_tool_events_around_execute_command():
    chat_client = FakeChatClient(
        [
            ChatMessage(
                role="assistant", content="",
                tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
            ),
            ChatMessage(role="assistant", content="today is monday"),
        ]
    )
    tool = FakeTool(result_text="exit_code=0\nstdout=Monday\nstderr=")
    tracer = FakeTracer()
    loop = make_loop(chat_client, tool=tool, tracer=tracer)

    loop.handle_message(chat_id=1, text="what day is it")

    assert tracer.event_types() == [
        "context_loaded", "agent_step_started", "llm_started", "llm_completed",
        "tool_requested", "tool_started", "tool_completed",
        "agent_step_started", "llm_started", "llm_completed", "final_answer",
    ]
    tool_requested_payload = tracer.calls[5][2]["payload"]
    assert tool_requested_payload == {"tool": "execute_command", "arguments": {"command": "date"}}
    tool_completed_payload = tracer.calls[7][2]["payload"]
    assert tool_completed_payload["exit_code"] == 0
    assert tool_completed_payload["stdout"] == "Monday" or "stdout" in tool_completed_payload
    assert tool_completed_payload["command"] == "date"
    assert tracer.calls[-1][1]["tool_calls"] == 1


def test_fail_trace_called_on_inference_error():
    chat_client = FakeChatClient([InferenceError("boom")])
    tracer = FakeTracer()
    loop = make_loop(chat_client, tracer=tracer)

    reply = loop.handle_message(chat_id=1, text="hi")

    assert reply == FALLBACK_REPLY
    assert tracer.calls[-1] == ("fail_trace", {"trace_id": "trace-1", "error_type": "InferenceError", "message": "boom"})


def test_non_inference_exception_calls_fail_trace_and_propagates():
    """Regression for final-branch-review finding #1: a non-InferenceError exception (e.g. a bug in the
    chat client, tool dispatch, or store) must still close the trace via fail_trace before propagating,
    so the trace row never gets stuck RUNNING forever. app/main.py's existing catch-all is what decides
    what the user sees; this only guarantees the trace is closed first."""
    chat_client = FakeChatClient([RuntimeError("unexpected boom")])
    tracer = FakeTracer()
    loop = make_loop(chat_client, tracer=tracer)

    with pytest.raises(RuntimeError, match="unexpected boom"):
        loop.handle_message(chat_id=1, text="hi")

    assert tracer.calls[-1] == (
        "fail_trace",
        {"trace_id": "trace-1", "error_type": "RuntimeError", "message": "unexpected boom"},
    )


def test_non_inference_exception_does_not_persist_assistant_message():
    chat_client = FakeChatClient([RuntimeError("unexpected boom")])
    store = ConversationStore(":memory:")
    loop = make_loop(chat_client, store=store)

    with pytest.raises(RuntimeError):
        loop.handle_message(chat_id=1, text="hi")

    conversation_id = store.active_conversation_id(chat_id=1)
    stored = store.recent_messages(conversation_id, limit=10)
    assert [(m.role, m.content) for m in stored] == [("user", "hi")]


def test_max_steps_trace_called_when_step_limit_reached():
    looping_call = ChatMessage(
        role="assistant", content="",
        tool_calls=(ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),),
    )
    chat_client = FakeChatClient([looping_call] * 3)
    tracer = FakeTracer()
    loop = make_loop(chat_client, max_steps=3, tracer=tracer)

    reply = loop.handle_message(chat_id=1, text="loop forever")

    assert reply == MAX_STEPS_REPLY
    assert tracer.calls[-1] == ("max_steps_trace", {"trace_id": "trace-1", "max_steps": 3})
