# telegram-llm-bot

`telegram-llm-bot` is a small educational Python 3.12+ project: a Telegram bot that runs a minimal
autonomous agent on top of a local LLM through Ollama. It is no longer a stateless one-shot responder — the
bot drives a bounded tool-calling loop (the "harness") backed by one universal tool, `execute_command`, and
a SQLite-backed conversation history per chat. See `CONTEXT.md` for the project's vocabulary (harness,
conversation, chat, skill) and `docs/adr/` for the design decisions behind the current shape, in particular
why the tool is named `execute_command` rather than `exec` and why the sandbox is "hardened in-container"
rather than a separate Docker sidecar today.

```text
User Message -> Telegram Bot API -> BotService -> AgentLoop -> Ollama (native tool-calling) -> Bot Reply
                                                       |
                                                       +--> execute_command (subprocess in the bot container)
                                                       +--> SQLite conversation memory
```

No Kubernetes, managed database, Redis, vector database, queue, webhook receiver, or separate Agent Service
are used — see `CLAUDE.md` for the full non-goals list.

## Concept

Each Telegram chat has one active SQLite-backed conversation. Every incoming message is appended to that
conversation, and the agent loop is given the last `MAX_CONTEXT_MESSAGES` messages as context (plus the
system prompt) before calling the model:

```text
input: chat_id + latest text message
context: last MAX_CONTEXT_MESSAGES messages from the chat's active conversation
output: one generated reply, itself appended back to the conversation
```

Sending `/new` closes the current conversation and starts a fresh one for that chat. Older messages are not
deleted, they simply stop being read as context. Within a single incoming message, the agent loop may call
`execute_command` more than once (up to `AGENT_MAX_STEPS` rounds) before producing a final reply — for
example to read a skill file and then act on it.

This keeps the code easy to study and easy to extend later. Telegram integration, the agent harness, and
inference are separated so another inference provider, such as vLLM, can be added without rewriting Telegram
polling.

## Features

- Direct Telegram Bot API integration over HTTP.
- Long polling with `getUpdates`.
- Replies with `sendMessage`.
- In-memory Telegram update offset during process runtime.
- A bounded agent loop (`app/agent/loop.py`) that calls the model, dispatches any tool calls it requests,
  and feeds results back until a final answer or a max-steps guard trips.
- Native Ollama tool-calling over `/api/chat`, not free-form text parsing.
- One universal tool, `execute_command`, that runs a shell command inside the bot's own container with a
  timeout, truncated output, a fixed workspace `cwd`, and a restricted environment allowlist.
- Skill files under `skills/` (Markdown, Type A single-CLI and Type B multi-step) that the model discovers
  and reads itself via `execute_command` (`ls skills/`, `cat skills/<name>.md`) rather than a dedicated tool.
- SQLite-backed conversation memory, one active conversation per chat, trimmed to the last
  `MAX_CONTEXT_MESSAGES` messages sent to the model.
- `/new` command to start a fresh conversation for a chat without deleting prior history.
- Docker Compose with `telegram-bot` and `ollama` services.
- Environment-based configuration.
- Non-root bot container.
- Basic logging, error handling, and tests.
- Native Telegram "typing..." indicator while waiting for a reply.
- Optional `chat_id` allowlist to reject messages from any chat other than the configured one.
- A factual system prompt instructing the model to say "I don't know" instead of guessing.

## Project Layout

```text
app/
  main.py                    # entry point, dependency wiring, polling loop, chat_id allowlist, /new
  config.py                  # environment parsing and validation
  telegram/
    client.py                # Telegram HTTP API client (getUpdates, sendMessage, sendChatAction)
    updates.py               # update parsing and offset handling
    typing_indicator.py      # background "typing..." chat action while waiting for a reply
  application/
    bot_service.py           # thin Telegram-agnostic entry point delegating to the agent loop
  agent/
    loop.py                  # AgentLoop: bounded tool-calling harness
    system_prompt.py         # response rules + tool + skill-discovery guidance
  tools/
    exec_tool.py              # ExecTool ("execute_command"), ExecResult, build_exec_env()
  memory/
    store.py                  # ConversationStore: SQLite conversations/messages, /new support
  inference/
    base.py                  # InferenceError, shared inference contract
    ollama_chat.py            # OllamaChatClient, native /api/chat tool-calling
skills/                        # Markdown skill files the model reads via execute_command
tests/                        # pytest test suite
docs/adr/                      # architecture decision records for the agent harness
docs/specs/                    # dated spec addenda on top of Spec.md
docker-compose.yml
Dockerfile
.env.example
```

## Requirements

- Docker and Docker Compose.
- Telegram bot token from BotFather.
- Enough disk space for the selected Ollama model.

For local test runs without Docker, use Python 3.12+ and install the development dependencies.

## Configuration

Create `.env` from the example:

```bash
cp .env.example .env
```

Set the required values:

```text
TELEGRAM_BOT_TOKEN=123456:your-telegram-bot-token
OLLAMA_MODEL=qwen3:1.7b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
ALLOWED_CHAT_ID=
TYPING_ACTION_INTERVAL_SECONDS=4
AGENT_MAX_STEPS=8
MAX_CONTEXT_MESSAGES=30
EXEC_TIMEOUT_SECONDS=20
EMAIL_IMAP_HOST=
EMAIL_IMAP_PORT=993
EMAIL_ADDRESS=
EMAIL_APP_PASSWORD=
```

`docker-compose.yml` sets `OLLAMA_BASE_URL` to `http://ollama:11434` for the bot container.

`ALLOWED_CHAT_ID` restricts the bot to a single Telegram chat. Leave it empty during development (the bot
will reply to any chat and log a warning); set it to your chat's numeric id in production so messages from
any other chat get a short "Доступ ограничен." reply instead of reaching the LLM. `TYPING_ACTION_INTERVAL_SECONDS`
controls how often the bot re-sends the Telegram "typing..." status while waiting for a reply (must stay
below Telegram's ~5 second status TTL).

`AGENT_MAX_STEPS` bounds how many model-call/tool-call rounds the agent loop runs for a single incoming
message before it gives up and returns a "couldn't finish in time" reply. `MAX_CONTEXT_MESSAGES` caps how
many recent messages from the chat's active conversation are sent to the model as context on each turn.
`EXEC_TIMEOUT_SECONDS` is the per-call timeout for the `execute_command` tool; output beyond a fixed
character limit is truncated before being returned to the model. `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`,
`EMAIL_ADDRESS`, and `EMAIL_APP_PASSWORD` are optional and only needed for the `email` skill under `skills/`;
when set, they are the only extra variables passed into the `execute_command` subprocess environment (see
`app/tools/exec_tool.py:build_exec_env`) — the tool never inherits the bot's full process environment, so a
model-issued command cannot see `TELEGRAM_BOT_TOKEN` or other secrets it has no reason to need. Two more
variables have defaults in `app/config.py` and normally do not need to be set: `EXEC_WORKSPACE_DIR`
(`/app/workspace`, the fixed `cwd` for `execute_command`) and `MEMORY_DB_PATH` (`/app/data/memory.sqlite3`,
the SQLite conversation store).

Never commit a real Telegram token.

## Quick Start

Start the services:

```bash
docker compose up -d --build
```

Pull the configured model into the Ollama volume:

```bash
docker compose exec ollama ollama pull qwen3:1.7b
```

Check that the model is installed:

```bash
docker compose exec ollama ollama list
```

Watch the bot logs:

```bash
docker compose logs -f telegram-bot
```

Send a text message to your Telegram bot. The bot should forward the text to Ollama and send the generated reply back to the same chat.

## Local Development

Create and activate a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

Run tests:

```bash
pytest
```

Run the application locally only if `OLLAMA_BASE_URL` points to a reachable Ollama server:

```bash
python -m app.main
```

## Troubleshooting

### Telegram returns 401 Unauthorized

The bot token is not accepted by Telegram. Verify `TELEGRAM_BOT_TOKEN` in `.env`, recreate the container after changing it, and confirm the token was not revoked in BotFather:

```bash
docker compose up -d --force-recreate telegram-bot
docker compose logs --tail=100 telegram-bot
```

### Bot replies with a local model error message

The Telegram side is working, but inference failed. Check Ollama logs and installed models:

```bash
docker compose logs --tail=100 ollama
docker compose exec ollama ollama list
```

If the configured model is missing, pull it:

```bash
docker compose exec ollama ollama pull qwen3:1.7b
```

If `.env` uses a different `OLLAMA_MODEL`, pull that exact model name.

### Ollama returns 404 for `/api/chat`

Most often this means the requested model is not installed in the current Docker volume:

```text
{"error":"model 'qwen3:1.7b' not found"}
```

Install the model with `ollama pull` inside the `ollama` service.

## Security Notes

- Secrets are read from environment variables.
- The Telegram token is never hardcoded.
- The bot container runs as a non-root user.
- Docker Compose does not mount the Docker socket.
- Docker Compose does not mount the host filesystem into the bot.

## Future Extension

The code is shaped so the inference and execution layers can be replaced later without a rewrite:

```text
Telegram layer -> BotService -> AgentLoop -> OllamaChatClient
                                    |
                                    +--> execute_command (in-process subprocess, today)
```

A future vLLM provider or separate Agent Service should implement the same tool-calling chat boundary while
keeping Telegram polling and message handling unchanged.

The next concrete isolation step for `execute_command`, documented but not built, is a dedicated
`exec-runner` sidecar service that holds the Docker socket (only that container, never `telegram-bot`) and
spins up a short-lived `--rm --network none` container per tool call, instead of running the command as a
subprocess inside the bot's own container. See `docs/adr/0003-hardened-in-container-exec.md` for why that
step was deferred rather than built now.

Any further multi-process, ManBot-style evolution (separate Orchestrator/Planner/Executor/Services
processes, JSONL message passing) is intentionally out of scope for this repository and would happen in a
separate future repository instead — see `docs/adr/0001-single-process-agent-loop.md` and
`PROJECT_UNDERSTANDING_RU.md` for that vocabulary, used here as inspiration only, not a target shape.

Before adding larger systems such as MCP, RAG, additional memory backends, or cloud deployment, read the
project notes in `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `Prompt.md`, `Spec.md`, and `spec2.md`. Feature-level
additions on top of `Spec.md` (typing indicator, chat allowlist, factual system prompt) are documented in
`docs/specs/2026-08-22-interactive-hardening.md`.
