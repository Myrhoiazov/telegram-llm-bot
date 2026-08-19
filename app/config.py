"""Environment-based configuration for the bot."""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    ollama_base_url: str
    ollama_model: str
    poll_timeout_seconds: int
    request_timeout_seconds: int
    log_level: str


_DEFAULTS = {
    "OLLAMA_BASE_URL": "http://ollama:11434",
    "OLLAMA_MODEL": "qwen3:1.7b",
    "POLL_TIMEOUT_SECONDS": "30",
    "REQUEST_TIMEOUT_SECONDS": "60",
    "LOG_LEVEL": "INFO",
}


def load_config(env: dict[str, str] | None = None) -> Config:
    source = env if env is not None else os.environ

    token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN is required")

    ollama_base_url = source.get("OLLAMA_BASE_URL", _DEFAULTS["OLLAMA_BASE_URL"]).strip()
    if not ollama_base_url:
        raise ConfigError("OLLAMA_BASE_URL must not be empty")

    ollama_model = source.get("OLLAMA_MODEL", _DEFAULTS["OLLAMA_MODEL"]).strip()
    if not ollama_model:
        raise ConfigError("OLLAMA_MODEL must not be empty")

    poll_timeout_seconds = _parse_positive_int(
        source, "POLL_TIMEOUT_SECONDS", _DEFAULTS["POLL_TIMEOUT_SECONDS"]
    )
    request_timeout_seconds = _parse_positive_int(
        source, "REQUEST_TIMEOUT_SECONDS", _DEFAULTS["REQUEST_TIMEOUT_SECONDS"]
    )

    log_level = (source.get("LOG_LEVEL", _DEFAULTS["LOG_LEVEL"]).strip() or "INFO").upper()

    return Config(
        telegram_bot_token=token,
        ollama_base_url=ollama_base_url.rstrip("/"),
        ollama_model=ollama_model,
        poll_timeout_seconds=poll_timeout_seconds,
        request_timeout_seconds=request_timeout_seconds,
        log_level=log_level,
    )


def _parse_positive_int(source: dict[str, str], key: str, default: str) -> int:
    raw = source.get(key, default).strip() or default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{key} must be positive, got {value}")
    return value
