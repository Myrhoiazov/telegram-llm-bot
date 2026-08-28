from app.telegram.client import TelegramClient


class FakeResponse:
    def __init__(self, payload=None, ok=True, status_code=200, content=b""):
        self._payload = payload if payload is not None else {"ok": True, "result": True}
        self.ok = ok
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.post_calls = []
        self.get_calls = []
        self.post_responses = []
        self.get_responses = []

    def post(self, url, params=None, json=None, timeout=None):
        self.post_calls.append({"url": url, "params": params, "json": json, "timeout": timeout})
        if self.post_responses:
            return self.post_responses.pop(0)
        return FakeResponse()

    def get(self, url, timeout=None):
        self.get_calls.append({"url": url, "timeout": timeout})
        if self.get_responses:
            return self.get_responses.pop(0)
        return FakeResponse(content=b"file-bytes")


def test_send_message_accepts_reply_markup():
    session = FakeSession()
    client = TelegramClient("token", poll_timeout_seconds=30, request_timeout_seconds=60, session=session)
    reply_markup = {"inline_keyboard": [[{"text": "Voice", "callback_data": "mode:voice"}]]}

    client.send_message(555, "hello", reply_markup=reply_markup)

    assert session.post_calls == [
        {
            "url": "https://api.telegram.org/bottoken/sendMessage",
            "params": None,
            "json": {"chat_id": 555, "text": "hello", "reply_markup": reply_markup},
            "timeout": 60,
        }
    ]


def test_answer_callback_query_posts_callback_id():
    session = FakeSession()
    client = TelegramClient("token", poll_timeout_seconds=30, request_timeout_seconds=60, session=session)

    client.answer_callback_query("callback-1")

    assert session.post_calls[0]["url"] == "https://api.telegram.org/bottoken/answerCallbackQuery"
    assert session.post_calls[0]["json"] == {"callback_query_id": "callback-1"}


def test_get_file_returns_telegram_file_result():
    session = FakeSession()
    session.post_responses.append(
        FakeResponse(payload={"ok": True, "result": {"file_id": "abc", "file_path": "voice/file.oga"}})
    )
    client = TelegramClient("token", poll_timeout_seconds=30, request_timeout_seconds=60, session=session)

    result = client.get_file("abc")

    assert result == {"file_id": "abc", "file_path": "voice/file.oga"}
    assert session.post_calls[0]["url"] == "https://api.telegram.org/bottoken/getFile"
    assert session.post_calls[0]["json"] == {"file_id": "abc"}


def test_download_file_uses_file_api_url():
    session = FakeSession()
    session.get_responses.append(FakeResponse(content=b"voice-bytes"))
    client = TelegramClient("token", poll_timeout_seconds=30, request_timeout_seconds=60, session=session)

    content = client.download_file("voice/file.oga")

    assert content == b"voice-bytes"
    assert session.get_calls == [
        {"url": "https://api.telegram.org/file/bottoken/voice/file.oga", "timeout": 60}
    ]
