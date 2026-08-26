from app.telemetry.redact import redact_payload, redact_text


def test_redact_text_replaces_known_secret():
    assert redact_text("token is abc123 in the log", ["abc123"]) == "token is *** in the log"


def test_redact_text_ignores_empty_secret_list():
    assert redact_text("nothing secret here", []) == "nothing secret here"


def test_redact_payload_redacts_nested_strings():
    payload = {
        "command": "curl -H 'Authorization: abc123' https://example.com",
        "arguments": {"password": "abc123"},
        "list": ["abc123", "safe"],
        "count": 3,
    }

    redacted = redact_payload(payload, ["abc123"])

    assert redacted["command"] == "curl -H 'Authorization: ***' https://example.com"
    assert redacted["arguments"]["password"] == "***"
    assert redacted["list"] == ["***", "safe"]
    assert redacted["count"] == 3


def test_redact_text_handles_overlapping_substring_secrets():
    """Regression: longer secrets must be redacted before their substrings.
    If ["abc", "abc123xyz"] is given and "abc" is processed first,
    the text "abc123xyz" becomes "***123xyz", so "abc123xyz" no longer matches.
    Sorting by descending length prevents this leakage."""
    # Note: secrets list order is ["abc", "abc123xyz"] — shorter first
    result = redact_text("token abc123xyz in log", ["abc", "abc123xyz"])
    # Both should be fully redacted; no "123xyz" leakage
    assert result == "token *** in log"
    assert "123xyz" not in result
