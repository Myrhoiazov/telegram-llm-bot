from app.config import Config
from app.tools.exec_tool import ExecTool, build_exec_env


def make_tool(tmp_path, timeout_seconds=5):
    return ExecTool(workspace_dir=str(tmp_path), timeout_seconds=timeout_seconds, env={"PATH": "/usr/bin:/bin"})


def test_execute_command_returns_stdout_and_exit_code(tmp_path):
    tool = make_tool(tmp_path)

    result = tool.run("echo hello")

    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    assert result.timed_out is False


def test_execute_command_captures_nonzero_exit_code(tmp_path):
    tool = make_tool(tmp_path)

    result = tool.run("exit 3")

    assert result.exit_code == 3


def test_execute_command_runs_in_workspace_dir(tmp_path):
    tool = make_tool(tmp_path)

    result = tool.run("pwd")

    assert result.stdout.strip() == str(tmp_path)


def test_execute_command_times_out(tmp_path):
    tool = make_tool(tmp_path, timeout_seconds=1)

    result = tool.run("sleep 5")

    assert result.timed_out is True


def test_to_tool_content_truncates_long_output(tmp_path):
    tool = make_tool(tmp_path)

    result = tool.run("python3 -c \"print('x' * 5000)\"")
    content = result.to_tool_content()

    assert len(content) < 5000
    assert "...[truncated]" in content


def test_schema_declares_command_parameter(tmp_path):
    tool = make_tool(tmp_path)

    schema = tool.schema()

    assert schema["function"]["name"] == "execute_command"
    assert schema["function"]["parameters"]["required"] == ["command"]


def test_build_exec_env_omits_email_vars_when_not_configured():
    config = Config(
        telegram_bot_token="t", ollama_base_url="http://ollama:11434", ollama_model="m",
        poll_timeout_seconds=30, request_timeout_seconds=60, log_level="INFO",
        allowed_chat_id=None, typing_action_interval_seconds=4, agent_max_steps=8,
        max_context_messages=30, exec_timeout_seconds=20, exec_workspace_dir="/app/workspace",
        memory_db_path="/app/data/memory.sqlite3", email_imap_host="", email_imap_port=993,
        email_address="", email_app_password="",
    )

    env = build_exec_env(config)

    assert "EMAIL_IMAP_HOST" not in env
    assert "PATH" in env


def test_build_exec_env_includes_email_vars_when_configured():
    config = Config(
        telegram_bot_token="t", ollama_base_url="http://ollama:11434", ollama_model="m",
        poll_timeout_seconds=30, request_timeout_seconds=60, log_level="INFO",
        allowed_chat_id=None, typing_action_interval_seconds=4, agent_max_steps=8,
        max_context_messages=30, exec_timeout_seconds=20, exec_workspace_dir="/app/workspace",
        memory_db_path="/app/data/memory.sqlite3", email_imap_host="imap.example.com",
        email_imap_port=993, email_address="bot@example.com", email_app_password="secret",
    )

    env = build_exec_env(config)

    assert env["EMAIL_IMAP_HOST"] == "imap.example.com"
    assert env["EMAIL_IMAP_PORT"] == "993"
    assert env["EMAIL_ADDRESS"] == "bot@example.com"
    assert env["EMAIL_APP_PASSWORD"] == "secret"
    assert "TELEGRAM_BOT_TOKEN" not in env
