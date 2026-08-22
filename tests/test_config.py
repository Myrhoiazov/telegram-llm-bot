import pytest

from app.config import Config, ConfigError, load_config


def test_load_config_with_all_variables_set():
    env = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "OLLAMA_BASE_URL": "http://ollama:11434",
        "OLLAMA_MODEL": "qwen3:1.7b",
        "POLL_TIMEOUT_SECONDS": "20",
        "REQUEST_TIMEOUT_SECONDS": "45",
        "LOG_LEVEL": "debug",
        "ALLOWED_CHAT_ID": "555",
        "TYPING_ACTION_INTERVAL_SECONDS": "3",
    }

    config = load_config(env)

    assert config == Config(
        telegram_bot_token="test-token",
        ollama_base_url="http://ollama:11434",
        ollama_model="qwen3:1.7b",
        poll_timeout_seconds=20,
        request_timeout_seconds=45,
        log_level="DEBUG",
        allowed_chat_id=555,
        typing_action_interval_seconds=3,
    )


def test_load_config_applies_defaults_when_optional_vars_missing():
    env = {"TELEGRAM_BOT_TOKEN": "test-token"}

    config = load_config(env)

    assert config.ollama_base_url == "http://ollama:11434"
    assert config.ollama_model == "qwen3:1.7b"
    assert config.poll_timeout_seconds == 30
    assert config.request_timeout_seconds == 60
    assert config.log_level == "INFO"
    assert config.allowed_chat_id is None
    assert config.typing_action_interval_seconds == 4


def test_load_config_allowed_chat_id_invalid_raises():
    env = {"TELEGRAM_BOT_TOKEN": "test-token", "ALLOWED_CHAT_ID": "not-a-number"}

    with pytest.raises(ConfigError):
        load_config(env)


def test_load_config_strips_trailing_slash_from_base_url():
    env = {"TELEGRAM_BOT_TOKEN": "test-token", "OLLAMA_BASE_URL": "http://ollama:11434/"}

    config = load_config(env)

    assert config.ollama_base_url == "http://ollama:11434"


def test_load_config_missing_token_raises():
    with pytest.raises(ConfigError):
        load_config({})


def test_load_config_invalid_integer_raises():
    env = {"TELEGRAM_BOT_TOKEN": "test-token", "POLL_TIMEOUT_SECONDS": "not-a-number"}

    with pytest.raises(ConfigError):
        load_config(env)
