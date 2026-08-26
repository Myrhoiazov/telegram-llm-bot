"""The execute_command tool: runs a shell command in a fixed workspace with hard limits."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Config

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 4000


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_ms: int
    truncated: bool

    def to_tool_content(self) -> str:
        if self.timed_out:
            return f"timed_out=true exit_code={self.exit_code}\nstdout={self.stdout}\nstderr={self.stderr}"
        return f"exit_code={self.exit_code}\nstdout={self.stdout}\nstderr={self.stderr}"


def _truncate(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False
    return text[:MAX_OUTPUT_CHARS] + "...[truncated]", True


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


class ExecTool:
    name = "execute_command"

    def __init__(self, workspace_dir: str, timeout_seconds: int, env: dict[str, str]) -> None:
        self._workspace_dir = Path(workspace_dir)
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        self._timeout_seconds = timeout_seconds
        self._env = env

    def run(self, command: str) -> ExecResult:
        start = time.monotonic()
        try:
            completed = subprocess.run(
                ["/bin/sh", "-c", command],
                cwd=self._workspace_dir,
                env=self._env,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=self._timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning("execute_command timed out: command=%r", command)
            stdout, stdout_truncated = _truncate(_decode(exc.stdout))
            stderr, stderr_truncated = _truncate(_decode(exc.stderr))
            return ExecResult(
                exit_code=-1,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
                duration_ms=duration_ms,
                truncated=stdout_truncated or stderr_truncated,
            )
        duration_ms = int((time.monotonic() - start) * 1000)
        stdout, stdout_truncated = _truncate(completed.stdout)
        stderr, stderr_truncated = _truncate(completed.stderr)
        return ExecResult(
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            timed_out=False,
            duration_ms=duration_ms,
            truncated=stdout_truncated or stderr_truncated,
        )

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Executes a command line instruction inside the bot's workspace directory and "
                    "returns its exit code, stdout, and stderr. Use it for anything requiring real "
                    "system access: checking the date/time, calling public HTTP APIs with curl, "
                    "reading skill files under skills/, or running short scripts."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute, e.g. 'curl wttr.in/Minsk?0'",
                        }
                    },
                    "required": ["command"],
                },
            },
        }


def build_exec_env(config: "Config") -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if config.email_imap_host:
        env["EMAIL_IMAP_HOST"] = config.email_imap_host
        env["EMAIL_IMAP_PORT"] = str(config.email_imap_port)
        env["EMAIL_ADDRESS"] = config.email_address
        env["EMAIL_APP_PASSWORD"] = config.email_app_password
    return env
