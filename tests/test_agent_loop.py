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
    def __init__(self, text):
        self._text = text

    def to_tool_content(self):
        return self._text


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


def make_loop(chat_client, tool=None, store=None, max_steps=8, max_context_messages=30):
    return AgentLoop(
        chat_client=chat_client,
        tool=tool or FakeTool(),
        store=store or ConversationStore(":memory:"),
        max_steps=max_steps,
        max_context_messages=max_context_messages,
        system_prompt="SYSTEM",
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
