from app.config import Config
from app.main import ACCESS_DENIED_REPLY, NEW_CHAT_REPLY, UNEXPECTED_ERROR_REPLY, run_polling_loop


def make_config(allowed_chat_id):
    return Config(
        telegram_bot_token="test-token",
        ollama_base_url="http://ollama:11434",
        ollama_model="qwen3:1.7b",
        poll_timeout_seconds=30,
        request_timeout_seconds=60,
        log_level="INFO",
        allowed_chat_id=allowed_chat_id,
        typing_action_interval_seconds=0.01,
        agent_max_steps=8,
        max_context_messages=30,
        exec_timeout_seconds=20,
        exec_workspace_dir="/tmp/workspace",
        memory_db_path=":memory:",
        email_imap_host="",
        email_imap_port=993,
        email_address="",
        email_app_password="",
    )


class FakeBotService:
    def __init__(self, reply="ok"):
        self._reply = reply
        self.calls = []

    def handle_message(self, chat_id, text):
        self.calls.append((chat_id, text))
        return self._reply


class FakeStore:
    def __init__(self):
        self.new_conversation_calls = []

    def start_new_conversation(self, chat_id):
        self.new_conversation_calls.append(chat_id)
        return 1


class FailingBotService:
    def handle_message(self, chat_id, text):
        raise RuntimeError("boom")


class FailingStore:
    def __init__(self):
        self.new_conversation_calls = []

    def start_new_conversation(self, chat_id):
        self.new_conversation_calls.append(chat_id)
        raise RuntimeError("boom")


class FakeTelegramClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.sent_messages = []
        self.chat_actions = []

    def get_updates(self, offset):
        if not self._batches:
            raise KeyboardInterrupt
        return self._batches.pop(0)

    def send_message(self, chat_id, text):
        self.sent_messages.append((chat_id, text))

    def send_chat_action(self, chat_id, action="typing"):
        self.chat_actions.append((chat_id, action))


def _updates_payload(chat_id, text, update_id=1):
    return {
        "ok": True,
        "result": [
            {
                "update_id": update_id,
                "message": {"chat": {"id": chat_id}, "text": text},
            }
        ],
    }


def test_message_from_allowed_chat_is_handled():
    client = FakeTelegramClient([_updates_payload(555, "hi")])
    bot_service = FakeBotService(reply="hello back")
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert bot_service.calls == [(555, "hi")]
    assert client.sent_messages == [(555, "hello back")]


def test_message_from_disallowed_chat_is_rejected_without_calling_llm():
    client = FakeTelegramClient([_updates_payload(999, "hi")])
    bot_service = FakeBotService(reply="hello back")
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert bot_service.calls == []
    assert client.sent_messages == [(999, ACCESS_DENIED_REPLY)]


def test_allowed_chat_id_none_accepts_any_chat():
    client = FakeTelegramClient([_updates_payload(42, "hi")])
    bot_service = FakeBotService(reply="hello back")
    store = FakeStore()
    config = make_config(allowed_chat_id=None)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert bot_service.calls == [(42, "hi")]
    assert client.sent_messages == [(42, "hello back")]


def test_new_command_starts_new_conversation_without_calling_agent():
    client = FakeTelegramClient([_updates_payload(555, "/new")])
    bot_service = FakeBotService(reply="should not be used")
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert bot_service.calls == []
    assert store.new_conversation_calls == [555]
    assert client.sent_messages == [(555, NEW_CHAT_REPLY)]


def test_new_command_from_disallowed_chat_is_still_rejected():
    client = FakeTelegramClient([_updates_payload(999, "/new")])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert store.new_conversation_calls == []
    assert client.sent_messages == [(999, ACCESS_DENIED_REPLY)]


def test_bot_service_exception_does_not_crash_polling_loop():
    client = FakeTelegramClient([_updates_payload(555, "hi")])
    bot_service = FailingBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.sent_messages == [(555, UNEXPECTED_ERROR_REPLY)]


def test_store_start_new_conversation_exception_does_not_crash_polling_loop():
    client = FakeTelegramClient([_updates_payload(555, "/new")])
    bot_service = FakeBotService()
    store = FailingStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert store.new_conversation_calls == [555]
    assert client.sent_messages == []
