import pytest
import requests

from app.inference.base import InferenceError
from app.inference.ollama_chat import ChatMessage, OllamaChatClient, ToolCall


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, raise_json=False):
        self.status_code = status_code
        self.ok = status_code < 400
        self._json_data = json_data
        self._raise_json = raise_json

    def json(self):
        if self._raise_json:
            raise ValueError("invalid json")
        return self._json_data


class _FakeSession:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception
        self.last_call = None

    def post(self, url, json=None, timeout=None):
        self.last_call = {"url": url, "json": json, "timeout": timeout}
        if self._exception is not None:
            raise self._exception
        return self._response


def make_client(session):
    return OllamaChatClient("http://ollama:11434", "qwen3:1.7b", 30, session=session)


def test_chat_parses_final_answer_without_tool_calls():
    session = _FakeSession(
        response=_FakeResponse(json_data={"message": {"role": "assistant", "content": "hi there"}})
    )
    client = make_client(session)

    result = client.chat([{"role": "user", "content": "hi"}], tools=[])

    assert result == ChatMessage(role="assistant", content="hi there", tool_calls=())
    assert session.last_call["url"] == "http://ollama:11434/api/chat"
    assert session.last_call["json"]["stream"] is False


def test_chat_parses_tool_calls():
    session = _FakeSession(
        response=_FakeResponse(
            json_data={
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {"name": "execute_command", "arguments": {"command": "date"}},
                        }
                    ],
                }
            }
        )
    )
    client = make_client(session)

    result = client.chat([{"role": "user", "content": "what time is it"}], tools=[{"type": "function"}])

    assert result.content == ""
    assert result.tool_calls == (ToolCall(id="call_1", name="execute_command", arguments={"command": "date"}),)


def test_chat_raises_on_network_error():
    session = _FakeSession(exception=requests.ConnectionError("boom"))
    client = make_client(session)

    with pytest.raises(InferenceError):
        client.chat([{"role": "user", "content": "hi"}], tools=[])


def test_chat_raises_on_http_error_status():
    session = _FakeSession(response=_FakeResponse(status_code=500, json_data={}))
    client = make_client(session)

    with pytest.raises(InferenceError):
        client.chat([{"role": "user", "content": "hi"}], tools=[])


def test_chat_raises_on_invalid_json():
    session = _FakeSession(response=_FakeResponse(raise_json=True))
    client = make_client(session)

    with pytest.raises(InferenceError):
        client.chat([{"role": "user", "content": "hi"}], tools=[])


def test_chat_raises_when_message_missing():
    session = _FakeSession(response=_FakeResponse(json_data={}))
    client = make_client(session)

    with pytest.raises(InferenceError):
        client.chat([{"role": "user", "content": "hi"}], tools=[])
