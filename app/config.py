"""Environment-based configuration for the bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    allowed_chat_id: int | None
    typing_action_interval_seconds: int
    agent_max_steps: int
    max_context_messages: int
    exec_timeout_seconds: int
    exec_workspace_dir: str
    memory_db_path: str
    email_imap_host: str
    email_imap_port: int
    email_address: str
    email_app_password: str
    trace_enabled: bool = True
    dashboard_enabled: bool = True
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8080
    trace_max_list_limit: int = 100


_DEFAULTS = {
    "OLLAMA_BASE_URL": "http://ollama:11434",
    "OLLAMA_MODEL": "qwen3:1.7b",
    "POLL_TIMEOUT_SECONDS": "30",
    "REQUEST_TIMEOUT_SECONDS": "60",
    "LOG_LEVEL": "INFO",
    "TYPING_ACTION_INTERVAL_SECONDS": "4",
    "AGENT_MAX_STEPS": "8",
    "MAX_CONTEXT_MESSAGES": "30",
    "EXEC_TIMEOUT_SECONDS": "20",
    "EXEC_WORKSPACE_DIR": "/app/workspace",
    "MEMORY_DB_PATH": "/app/data/memory.sqlite3",
    "EMAIL_IMAP_PORT": "993",
    "TRACE_ENABLED": "true",
    "DASHBOARD_ENABLED": "true",
    "DASHBOARD_HOST": "0.0.0.0",
    "DASHBOARD_PORT": "8080",
    "TRACE_MAX_LIST_LIMIT": "100",
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

    allowed_chat_id = _parse_allowed_chat_id(source)
    typing_action_interval_seconds = _parse_positive_int(
        source, "TYPING_ACTION_INTERVAL_SECONDS", _DEFAULTS["TYPING_ACTION_INTERVAL_SECONDS"]
    )

    agent_max_steps = _parse_positive_int(source, "AGENT_MAX_STEPS", _DEFAULTS["AGENT_MAX_STEPS"])
    max_context_messages = _parse_positive_int(
        source, "MAX_CONTEXT_MESSAGES", _DEFAULTS["MAX_CONTEXT_MESSAGES"]
    )
    exec_timeout_seconds = _parse_positive_int(
        source, "EXEC_TIMEOUT_SECONDS", _DEFAULTS["EXEC_TIMEOUT_SECONDS"]
    )
    exec_workspace_dir = source.get("EXEC_WORKSPACE_DIR", _DEFAULTS["EXEC_WORKSPACE_DIR"]).strip()
    memory_db_path = source.get("MEMORY_DB_PATH", _DEFAULTS["MEMORY_DB_PATH"]).strip()
    email_imap_host = source.get("EMAIL_IMAP_HOST", "").strip()
    email_imap_port = _parse_positive_int(source, "EMAIL_IMAP_PORT", _DEFAULTS["EMAIL_IMAP_PORT"])
    email_address = source.get("EMAIL_ADDRESS", "").strip()
    email_app_password = source.get("EMAIL_APP_PASSWORD", "").strip()

    trace_enabled = _parse_bool(source, "TRACE_ENABLED", _DEFAULTS["TRACE_ENABLED"])
    dashboard_enabled = _parse_bool(source, "DASHBOARD_ENABLED", _DEFAULTS["DASHBOARD_ENABLED"])
    dashboard_host = source.get("DASHBOARD_HOST", _DEFAULTS["DASHBOARD_HOST"]).strip()
    dashboard_port = _parse_positive_int(source, "DASHBOARD_PORT", _DEFAULTS["DASHBOARD_PORT"])
    trace_max_list_limit = _parse_positive_int(
        source, "TRACE_MAX_LIST_LIMIT", _DEFAULTS["TRACE_MAX_LIST_LIMIT"]
    )

    return Config(
        telegram_bot_token=token,
        ollama_base_url=ollama_base_url.rstrip("/"),
        ollama_model=ollama_model,
        poll_timeout_seconds=poll_timeout_seconds,
        request_timeout_seconds=request_timeout_seconds,
        log_level=log_level,
        allowed_chat_id=allowed_chat_id,
        typing_action_interval_seconds=typing_action_interval_seconds,
        agent_max_steps=agent_max_steps,
        max_context_messages=max_context_messages,
        exec_timeout_seconds=exec_timeout_seconds,
        exec_workspace_dir=exec_workspace_dir,
        memory_db_path=memory_db_path,
        email_imap_host=email_imap_host,
        email_imap_port=email_imap_port,
        email_address=email_address,
        email_app_password=email_app_password,
        trace_enabled=trace_enabled,
        dashboard_enabled=dashboard_enabled,
        dashboard_host=dashboard_host,
        dashboard_port=dashboard_port,
        trace_max_list_limit=trace_max_list_limit,
    )


def _parse_allowed_chat_id(source: dict[str, str]) -> int | None:
    raw = source.get("ALLOWED_CHAT_ID", "").strip()
    if not raw:
        logger.warning(
            "ALLOWED_CHAT_ID is not set: the bot will reply to messages from any chat"
        )
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"ALLOWED_CHAT_ID must be an integer, got {raw!r}") from exc


def _parse_positive_int(source: dict[str, str], key: str, default: str) -> int:
    raw = source.get(key, default).strip() or default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigError(f"{key} must be positive, got {value}")
    return value


def _parse_bool(source: dict[str, str], key: str, default: str) -> bool:
    raw = (source.get(key, default).strip() or default).lower()
    if raw in ("true", "1", "yes"):
        return True
    if raw in ("false", "0", "no"):
        return False
    raise ConfigError(f"{key} must be a boolean (true/false), got {raw!r}")
