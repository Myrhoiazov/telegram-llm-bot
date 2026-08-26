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
        "AGENT_MAX_STEPS": "5",
        "MAX_CONTEXT_MESSAGES": "10",
        "EXEC_TIMEOUT_SECONDS": "7",
        "EXEC_WORKSPACE_DIR": "/tmp/workspace",
        "MEMORY_DB_PATH": "/tmp/memory.sqlite3",
        "EMAIL_IMAP_HOST": "imap.example.com",
        "EMAIL_IMAP_PORT": "1993",
        "EMAIL_ADDRESS": "bot@example.com",
        "EMAIL_APP_PASSWORD": "secret",
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
        agent_max_steps=5,
        max_context_messages=10,
        exec_timeout_seconds=7,
        exec_workspace_dir="/tmp/workspace",
        memory_db_path="/tmp/memory.sqlite3",
        email_imap_host="imap.example.com",
        email_imap_port=1993,
        email_address="bot@example.com",
        email_app_password="secret",
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
    assert config.agent_max_steps == 8
    assert config.max_context_messages == 30
    assert config.exec_timeout_seconds == 20
    assert config.exec_workspace_dir == "/app/workspace"
    assert config.memory_db_path == "/app/data/memory.sqlite3"
    assert config.email_imap_host == ""
    assert config.email_imap_port == 993
    assert config.email_address == ""
    assert config.email_app_password == ""


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


def test_load_config_applies_agent_memory_exec_email_defaults():
    env = {"TELEGRAM_BOT_TOKEN": "test-token"}

    config = load_config(env)

    assert config.agent_max_steps == 8
    assert config.max_context_messages == 30
    assert config.exec_timeout_seconds == 20
    assert config.exec_workspace_dir == "/app/workspace"
    assert config.memory_db_path == "/app/data/memory.sqlite3"
    assert config.email_imap_host == ""
    assert config.email_imap_port == 993
    assert config.email_address == ""
    assert config.email_app_password == ""


def test_load_config_reads_agent_memory_exec_email_overrides():
    env = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "AGENT_MAX_STEPS": "5",
        "MAX_CONTEXT_MESSAGES": "10",
        "EXEC_TIMEOUT_SECONDS": "7",
        "EXEC_WORKSPACE_DIR": "/tmp/workspace",
        "MEMORY_DB_PATH": "/tmp/memory.sqlite3",
        "EMAIL_IMAP_HOST": "imap.example.com",
        "EMAIL_IMAP_PORT": "1993",
        "EMAIL_ADDRESS": "bot@example.com",
        "EMAIL_APP_PASSWORD": "secret",
    }

    config = load_config(env)

    assert config.agent_max_steps == 5
    assert config.max_context_messages == 10
    assert config.exec_timeout_seconds == 7
    assert config.exec_workspace_dir == "/tmp/workspace"
    assert config.memory_db_path == "/tmp/memory.sqlite3"
    assert config.email_imap_host == "imap.example.com"
    assert config.email_imap_port == 1993
    assert config.email_address == "bot@example.com"
    assert config.email_app_password == "secret"


def test_load_config_applies_trace_and_dashboard_defaults():
    env = {"TELEGRAM_BOT_TOKEN": "test-token"}

    config = load_config(env)

    assert config.trace_enabled is True
    assert config.dashboard_enabled is True
    assert config.dashboard_host == "0.0.0.0"
    assert config.dashboard_port == 8080
    assert config.trace_max_list_limit == 100


def test_load_config_reads_trace_and_dashboard_overrides():
    env = {
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TRACE_ENABLED": "false",
        "DASHBOARD_ENABLED": "FALSE",
        "DASHBOARD_HOST": "127.0.0.1",
        "DASHBOARD_PORT": "9090",
        "TRACE_MAX_LIST_LIMIT": "250",
    }

    config = load_config(env)

    assert config.trace_enabled is False
    assert config.dashboard_enabled is False
    assert config.dashboard_host == "127.0.0.1"
    assert config.dashboard_port == 9090
    assert config.trace_max_list_limit == 250


def test_load_config_rejects_invalid_boolean():
    env = {"TELEGRAM_BOT_TOKEN": "test-token", "TRACE_ENABLED": "maybe"}

    with pytest.raises(ConfigError):
        load_config(env)
