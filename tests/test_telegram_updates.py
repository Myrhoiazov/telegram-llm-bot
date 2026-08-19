from app.telegram.updates import TextMessage, parse_updates


def test_parse_updates_extracts_text_message():
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 100,
                "message": {
                    "message_id": 1,
                    "chat": {"id": 555},
                    "text": "hello",
                },
            }
        ],
    }

    messages = parse_updates(payload)

    assert messages == [TextMessage(update_id=100, chat_id=555, text="hello")]


def test_parse_updates_ignores_message_without_text():
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 101,
                "message": {
                    "message_id": 2,
                    "chat": {"id": 555},
                    "photo": [{"file_id": "abc"}],
                },
            }
        ],
    }

    assert parse_updates(payload) == []


def test_parse_updates_ignores_non_message_update_types():
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 102,
                "edited_message": {
                    "message_id": 3,
                    "chat": {"id": 555},
                    "text": "edited",
                },
            }
        ],
    }

    assert parse_updates(payload) == []


def test_parse_updates_handles_empty_result():
    assert parse_updates({"ok": True, "result": []}) == []


def test_parse_updates_ignores_blank_text():
    payload = {
        "ok": True,
        "result": [
            {
                "update_id": 103,
                "message": {"chat": {"id": 555}, "text": "   "},
            }
        ],
    }

    assert parse_updates(payload) == []
