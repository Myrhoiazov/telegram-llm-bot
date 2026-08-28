from app.memory.store import ConversationStore, StoredMessage


def make_store() -> ConversationStore:
    return ConversationStore(":memory:")


def test_active_conversation_id_creates_conversation_when_none_exists():
    store = make_store()

    conversation_id = store.active_conversation_id(chat_id=555)

    assert isinstance(conversation_id, int)
    assert store.active_conversation_id(chat_id=555) == conversation_id


def test_start_new_conversation_creates_separate_history():
    store = make_store()
    first_id = store.active_conversation_id(chat_id=555)
    store.append_message(first_id, "user", "hello")

    second_id = store.start_new_conversation(chat_id=555)

    assert second_id != first_id
    assert store.active_conversation_id(chat_id=555) == second_id
    assert store.recent_messages(second_id, limit=10) == []
    assert store.recent_messages(first_id, limit=10) == [StoredMessage(role="user", content="hello")]


def test_append_and_recent_messages_roundtrip_oldest_first():
    store = make_store()
    conversation_id = store.active_conversation_id(chat_id=1)

    store.append_message(conversation_id, "user", "first")
    store.append_message(conversation_id, "assistant", "second")
    store.append_message(conversation_id, "user", "third")

    assert store.recent_messages(conversation_id, limit=10) == [
        StoredMessage(role="user", content="first"),
        StoredMessage(role="assistant", content="second"),
        StoredMessage(role="user", content="third"),
    ]


def test_recent_messages_respects_limit_keeping_most_recent():
    store = make_store()
    conversation_id = store.active_conversation_id(chat_id=1)
    for i in range(5):
        store.append_message(conversation_id, "user", f"msg{i}")

    result = store.recent_messages(conversation_id, limit=2)

    assert [m.content for m in result] == ["msg3", "msg4"]


def test_chat_input_mode_defaults_to_text():
    store = make_store()

    assert store.chat_input_mode(chat_id=555) == "text"


def test_chat_input_mode_roundtrips():
    store = make_store()

    store.set_chat_input_mode(chat_id=555, input_mode="voice")

    assert store.chat_input_mode(chat_id=555) == "voice"


def test_start_new_conversation_resets_chat_input_mode_to_text():
    store = make_store()
    store.set_chat_input_mode(chat_id=555, input_mode="voice")

    store.start_new_conversation(chat_id=555)

    assert store.chat_input_mode(chat_id=555) == "text"
