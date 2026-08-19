import pytest
import requests

from app.inference.base import InferenceError, TextGenerator
from app.inference.ollama import OllamaProvider


class FakeGenerator:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str) -> str:
        return self._reply


def test_fake_generator_satisfies_text_generator_contract():
    generator: TextGenerator = FakeGenerator("hi there")
    assert generator.generate("hello") == "hi there"


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


def test_ollama_provider_generate_returns_stripped_text():
    session = _FakeSession(response=_FakeResponse(json_data={"response": "  hello world  "}))
    provider = OllamaProvider("http://ollama:11434", "qwen3:1.7b", 30, session=session)

    result = provider.generate("hi")

    assert result == "hello world"
    assert session.last_call["url"] == "http://ollama:11434/api/generate"
    assert session.last_call["json"]["model"] == "qwen3:1.7b"
    assert session.last_call["json"]["prompt"] == "hi"
    assert session.last_call["json"]["stream"] is False


def test_ollama_provider_raises_on_network_error():
    session = _FakeSession(exception=requests.ConnectionError("boom"))
    provider = OllamaProvider("http://ollama:11434", "qwen3:1.7b", 30, session=session)

    with pytest.raises(InferenceError):
        provider.generate("hi")


def test_ollama_provider_raises_on_http_error_status():
    session = _FakeSession(response=_FakeResponse(status_code=500, json_data={}))
    provider = OllamaProvider("http://ollama:11434", "qwen3:1.7b", 30, session=session)

    with pytest.raises(InferenceError):
        provider.generate("hi")


def test_ollama_provider_raises_on_invalid_json():
    session = _FakeSession(response=_FakeResponse(raise_json=True))
    provider = OllamaProvider("http://ollama:11434", "qwen3:1.7b", 30, session=session)

    with pytest.raises(InferenceError):
        provider.generate("hi")


def test_ollama_provider_raises_on_empty_response_text():
    session = _FakeSession(response=_FakeResponse(json_data={"response": "   "}))
    provider = OllamaProvider("http://ollama:11434", "qwen3:1.7b", 30, session=session)

    with pytest.raises(InferenceError):
        provider.generate("hi")
