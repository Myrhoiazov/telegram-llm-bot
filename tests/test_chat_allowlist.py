from app.config import Config
from app.main import (
    ACCESS_DENIED_REPLY,
    CONTROL_REPLY_MARKUP,
    NEW_CHAT_REPLY,
    STT_DISABLED_REPLY,
    UNEXPECTED_ERROR_REPLY,
    VOICE_TOO_LONG_REPLY,
    run_polling_loop,
)


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
        self.mode_changes = []

    def start_new_conversation(self, chat_id):
        self.new_conversation_calls.append(chat_id)
        return 1

    def set_chat_input_mode(self, chat_id, input_mode):
        self.mode_changes.append((chat_id, input_mode))


class FailingBotService:
    def handle_message(self, chat_id, text):
        raise RuntimeError("boom")


class FailingStore:
    def __init__(self):
        self.new_conversation_calls = []

    def start_new_conversation(self, chat_id):
        self.new_conversation_calls.append(chat_id)
        raise RuntimeError("boom")

    def set_chat_input_mode(self, chat_id, input_mode):
        pass


class FakeTelegramClient:
    def __init__(self, batches):
        self._batches = list(batches)
        self.sent_messages = []
        self.chat_actions = []
        self.answered_callbacks = []
        self.get_file_calls = []
        self.download_file_calls = []

    def get_updates(self, offset):
        if not self._batches:
            raise KeyboardInterrupt
        return self._batches.pop(0)

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append((chat_id, text, reply_markup))

    def send_chat_action(self, chat_id, action="typing"):
        self.chat_actions.append((chat_id, action))

    def answer_callback_query(self, callback_query_id):
        self.answered_callbacks.append(callback_query_id)

    def get_file(self, file_id):
        self.get_file_calls.append(file_id)
        return {"file_path": "voice/file.oga"}

    def download_file(self, file_path):
        self.download_file_calls.append(file_path)
        return b"ogg-bytes"


class FakeVoiceProcessor:
    def __init__(self, text="распознанный текст"):
        self._text = text
        self.calls = []

    def process(self, audio_bytes):
        self.calls.append(audio_bytes)
        return self._text


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


def _callback_payload(chat_id, data, callback_query_id="callback-1", update_id=2):
    return {
        "ok": True,
        "result": [
            {
                "update_id": update_id,
                "callback_query": {
                    "id": callback_query_id,
                    "data": data,
                    "message": {"chat": {"id": chat_id}},
                },
            }
        ],
    }


def _voice_payload(chat_id, duration=12, update_id=3):
    return {
        "ok": True,
        "result": [
            {
                "update_id": update_id,
                "message": {
                    "chat": {"id": chat_id},
                    "voice": {
                        "file_id": "voice-file-id",
                        "file_unique_id": "voice-unique-id",
                        "duration": duration,
                        "mime_type": "audio/ogg",
                    },
                },
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
    assert client.sent_messages == [(555, "hello back", CONTROL_REPLY_MARKUP)]


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
    assert client.sent_messages == [(999, ACCESS_DENIED_REPLY, CONTROL_REPLY_MARKUP)]


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
    assert client.sent_messages == [(42, "hello back", CONTROL_REPLY_MARKUP)]


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
    assert store.mode_changes == [(555, "text")]
    assert client.sent_messages == [(555, NEW_CHAT_REPLY, CONTROL_REPLY_MARKUP)]


def test_new_command_with_bot_mention_starts_new_conversation():
    client = FakeTelegramClient([_updates_payload(555, "/new@my_test_bot")])
    bot_service = FakeBotService(reply="should not be used")
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert bot_service.calls == []
    assert store.new_conversation_calls == [555]
    assert store.mode_changes == [(555, "text")]
    assert client.sent_messages == [(555, NEW_CHAT_REPLY, CONTROL_REPLY_MARKUP)]


def test_command_with_new_prefix_is_not_treated_as_new_command():
    client = FakeTelegramClient([_updates_payload(555, "/newsletter")])
    bot_service = FakeBotService(reply="hello back")
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert store.new_conversation_calls == []
    assert bot_service.calls == [(555, "/newsletter")]


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
    assert client.sent_messages == [(999, ACCESS_DENIED_REPLY, CONTROL_REPLY_MARKUP)]


def test_bot_service_exception_does_not_crash_polling_loop():
    client = FakeTelegramClient([_updates_payload(555, "hi")])
    bot_service = FailingBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.sent_messages == [(555, UNEXPECTED_ERROR_REPLY, CONTROL_REPLY_MARKUP)]


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
    assert client.sent_messages == [(555, UNEXPECTED_ERROR_REPLY, CONTROL_REPLY_MARKUP)]


def test_voice_callback_switches_mode_and_acknowledges_callback():
    client = FakeTelegramClient([_callback_payload(555, "mode:voice")])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.answered_callbacks == ["callback-1"]
    assert store.mode_changes == [(555, "voice")]
    assert client.sent_messages == [(555, "Режим голосовых сообщений включен.", CONTROL_REPLY_MARKUP)]
    assert bot_service.calls == []


def test_voice_callback_when_stt_disabled_does_not_switch_mode():
    client = FakeTelegramClient([_callback_payload(555, "mode:voice")])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)
    config = Config(**{**config.__dict__, "stt_enabled": False})

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.answered_callbacks == ["callback-1"]
    assert store.mode_changes == []
    assert client.sent_messages == [(555, STT_DISABLED_REPLY, CONTROL_REPLY_MARKUP)]
    assert bot_service.calls == []


def test_new_callback_starts_conversation_switches_text_and_acknowledges_callback():
    client = FakeTelegramClient([_callback_payload(555, "mode:new")])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.answered_callbacks == ["callback-1"]
    assert store.new_conversation_calls == [555]
    assert store.mode_changes == [(555, "text")]
    assert client.sent_messages == [(555, NEW_CHAT_REPLY, CONTROL_REPLY_MARKUP)]
    assert bot_service.calls == []


def test_disallowed_callback_is_rejected_without_mode_change():
    client = FakeTelegramClient([_callback_payload(999, "mode:voice")])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config)
    except KeyboardInterrupt:
        pass

    assert client.answered_callbacks == ["callback-1"]
    assert store.mode_changes == []
    assert client.sent_messages == [(999, ACCESS_DENIED_REPLY, CONTROL_REPLY_MARKUP)]


def test_voice_message_is_transcribed_and_sent_to_bot_service():
    client = FakeTelegramClient([_voice_payload(555)])
    bot_service = FakeBotService(reply="ответ")
    store = FakeStore()
    voice_processor = FakeVoiceProcessor(text="что сегодня сделать")
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config, voice_processor=voice_processor)
    except KeyboardInterrupt:
        pass

    assert client.get_file_calls == ["voice-file-id"]
    assert client.download_file_calls == ["voice/file.oga"]
    assert voice_processor.calls == [b"ogg-bytes"]
    assert bot_service.calls == [(555, "что сегодня сделать")]
    assert client.sent_messages == [(555, "ответ", CONTROL_REPLY_MARKUP)]


def test_voice_message_over_duration_limit_is_rejected_before_download():
    client = FakeTelegramClient([_voice_payload(555, duration=61)])
    bot_service = FakeBotService()
    store = FakeStore()
    voice_processor = FakeVoiceProcessor()
    config = make_config(allowed_chat_id=555)

    try:
        run_polling_loop(client, bot_service, store, config, voice_processor=voice_processor)
    except KeyboardInterrupt:
        pass

    assert client.get_file_calls == []
    assert voice_processor.calls == []
    assert bot_service.calls == []
    assert client.sent_messages == [(555, VOICE_TOO_LONG_REPLY, CONTROL_REPLY_MARKUP)]


def test_voice_message_when_stt_disabled_is_rejected_before_download():
    client = FakeTelegramClient([_voice_payload(555)])
    bot_service = FakeBotService()
    store = FakeStore()
    config = make_config(allowed_chat_id=555)
    config = Config(**{**config.__dict__, "stt_enabled": False})

    try:
        run_polling_loop(client, bot_service, store, config, voice_processor=None)
    except KeyboardInterrupt:
        pass

    assert client.get_file_calls == []
    assert bot_service.calls == []
    assert client.sent_messages == [(555, STT_DISABLED_REPLY, CONTROL_REPLY_MARKUP)]
