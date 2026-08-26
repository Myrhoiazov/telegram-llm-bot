"""Strips known secret values out of telemetry payloads before they are persisted or broadcast."""
from __future__ import annotations

REDACTED = "***"


def redact_text(text: str, secrets: list[str]) -> str:
    redacted = text
    # Sort by descending length to avoid substring collisions:
    # if "abc" and "abc123xyz" are both secrets, we must replace the longer one first,
    # otherwise replacing "abc" would mutate the text and make "abc123xyz" no longer matchable.
    sorted_secrets = sorted(secrets, key=len, reverse=True)
    for secret in sorted_secrets:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    return redacted


def redact_payload(payload: dict, secrets: list[str]) -> dict:
    return {key: _redact_value(value, secrets) for key, value in payload.items()}


def _redact_value(value, secrets: list[str]):
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, dict):
        return redact_payload(value, secrets)
    if isinstance(value, list):
        return [_redact_value(item, secrets) for item in value]
    return value
