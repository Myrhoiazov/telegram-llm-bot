import importlib.util
from pathlib import Path


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_list_unread_headers_decodes_folded_mime_headers():
    module = load_module("list_unread_headers", "skills/email/scripts/list_unread_headers.py")
    raw = (
        b"From: =?utf-8?b?0J7Qv9C+0LLQtdGJ0LXQvdC40Y8g0L4g?=\r\n"
        b" =?utf-8?b?0LLQsNC60LDQvdGB0LjRj9GF?= <jobalerts-noreply@linkedin.com>\r\n"
        b"Subject: =?utf-8?b?wqtEZXZlbG9wZXJbNzVdXw==?=\r\n"
        b" =?utf-8?b?0Lhf0L3QtV/RgtC+0LvRjNC60L7Cuw==?=  Extra\r\n"
        b"Date: Fri, 28 Aug 2026 10:00:00 +0000\r\n"
        b"\r\n"
    )

    parsed = module.parse_header_message(b"42", raw)

    assert parsed["id"] == "42"
    assert parsed["from"] == "Оповещения о вакансиях <jobalerts-noreply@linkedin.com>"
    assert parsed["subject"] == "«Developer[75]_и_не_только» Extra"
    assert parsed["date"] == "Fri, 28 Aug 2026 10:00:00 +0000"
    assert "=?" not in parsed["from"]
    assert "=?" not in parsed["subject"]
