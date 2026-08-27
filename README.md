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
- Skill files under `skills/<name>/SKILL.md` (Markdown, Type A single-CLI and Type B multi-step), one folder
  per skill, that the model discovers and reads itself via `execute_command` (`ls skills/`,
  `cat skills/<name>/SKILL.md`) rather than a dedicated tool.
- SQLite-backed conversation memory, one active conversation per chat, trimmed to the last
  `MAX_CONTEXT_MESSAGES` messages sent to the model.
- `/new` command to start a fresh conversation for a chat without deleting prior history.
- Docker Compose for `telegram-bot`; `ollama` runs as a native host process, not a Compose service (see
  `CLAUDE.md` for why).
- Environment-based configuration.
- Non-root bot container.
- Basic logging, error handling, and tests.
- Native Telegram "typing..." indicator while waiting for a reply.
- Optional `chat_id` allowlist to reject messages from any chat other than the configured one.
- A factual system prompt instructing the model to say "I don't know" instead of guessing.
- A live agent trace dashboard (`app/telemetry/`, `app/dashboard/`) at `http://localhost:8080`, showing each
  message's harness steps as they happen and persisting them for later inspection.

## Agent Trace Dashboard

The bot ships a live, local observability dashboard for the agent loop: every incoming Telegram message
that reaches `AgentLoop` is recorded as a trace, and every step the harness takes inside that trace (model
calls, tool calls, the final answer) is recorded as an ordered event, streamed to the browser in real time
and persisted to SQLite for later inspection.

After `docker compose up -d --build`, open `http://localhost:8080` in a browser. The trace list is empty
until the bot handles its first message; send the bot any message and a new trace appears and fills in
live.

One trace is created per incoming Telegram message that is handed to `AgentLoop` (this does not include
`/new`, which is handled directly in `main.py` and never reaches the agent loop). A trace starts in status
`RUNNING` and ends in exactly one of `COMPLETED` (the loop produced a final answer), `FAILED` (the loop
raised an error), or `MAX_STEPS_REACHED` (the loop hit `AGENT_MAX_STEPS` without finishing).

Within a trace, events are emitted in this order (tool events repeat once per tool call):

```text
trace_started, context_loaded, agent_step_started,
llm_started, llm_completed,
tool_requested, tool_started, tool_completed,
final_answer, trace_completed, trace_failed, max_steps_reached
```

`skill_accessed` is also emitted, but only when a step actually reads a `skills/<name>/SKILL.md` file via
`execute_command`.

The dashboard and tracer are controlled by `TRACE_ENABLED`, `DASHBOARD_ENABLED`, `DASHBOARD_HOST`,
`DASHBOARD_PORT`, and `TRACE_MAX_LIST_LIMIT` — see `## Configuration` below for defaults and details.

`docker-compose.yml` publishes the dashboard port bound to `127.0.0.1` on the host by default, so it is not
reachable from outside the machine unless that binding is deliberately changed. `TELEGRAM_BOT_TOKEN` and
`EMAIL_APP_PASSWORD` are redacted to `***` in any event payload before it is persisted or displayed, so they
can never leak through a traced tool call or model response. The dashboard never shows model
chain-of-thought — only observable harness events (what step ran, what tool was called, what it returned,
how long it took).

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
  telemetry/
    events.py                # AgentEvent, trace status and event type constants
    tracer.py                # AgentTracer: emits events, tracks trace start/finish
    store.py                  # TraceStore: SQLite traces/events, list/read for the dashboard API
    broadcaster.py            # EventBroadcaster: fans out live events to connected SSE clients
    redact.py                 # secret redaction applied to event payloads before persist/broadcast
  dashboard/
    server.py                # build_dashboard_server(): ThreadingHTTPServer wiring
    api.py                    # REST endpoints (trace list/detail) + SSE stream handler
dashboard/
  index.html                  # dashboard single-page UI
  app.js                      # trace list, live SSE timeline rendering
  styles.css                  # dashboard styling
skills/<name>/SKILL.md         # one folder per skill; the model reads it via execute_command
tests/                        # pytest test suite
docs/adr/                      # architecture decision records for the agent harness
docs/specifications/           # Spec.md, spec2.md, PROJECT_UNDERSTANDING_RU.md, PROCESS_DIAGRAMS_RU.md
docs/specs/                    # dated spec addenda on top of Spec.md
docker-compose.yml
Dockerfile
.env.example
```

## Requirements

- Docker and Docker Compose (runs `telegram-bot`).
- Ollama installed and running natively on the host — e.g. `Ollama.app` on macOS (Metal-accelerated) — not
  inside Docker Compose. See `CLAUDE.md` for why.
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
OLLAMA_MODEL=qwen3:4b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=180
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
TRACE_ENABLED=true
DASHBOARD_ENABLED=true
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8080
TRACE_MAX_LIST_LIMIT=100
```

`docker-compose.yml` defaults `OLLAMA_BASE_URL` to `http://host.docker.internal:11434` (overridable via
`.env`), since Ollama runs natively on the host rather than as a Compose service — see `CLAUDE.md`.

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
`app/tools/exec_tool.py:build_exec_env`) — the tool does not inherit the bot's full process environment, so
an innocuous-looking model-issued command (e.g. plain `env`) will not accidentally dump `TELEGRAM_BOT_TOKEN`
or other secrets it has no reason to need. This allowlist is a hygiene measure against accidental exposure,
not a hard security boundary: `execute_command` still runs inside the same container/process as the bot
rather than a separate sandboxed process, so a sufficiently deliberate command could still reach the parent
process's environment. Real isolation is what the exec-runner sidecar described below is for. Two more
variables have defaults in `app/config.py` and normally do not need to be set: `EXEC_WORKSPACE_DIR`
(`/app/workspace`, the fixed `cwd` for `execute_command`) and `MEMORY_DB_PATH` (`/app/data/memory.sqlite3`,
the SQLite conversation store).

`TRACE_ENABLED` (default `true`) turns the agent tracer on: when enabled, `AgentLoop` emits an event per
harness step and each trace is persisted to the same SQLite database as conversation memory.
`DASHBOARD_ENABLED` (default `true`) turns on the local web dashboard server that serves the trace list, the
per-trace event timeline, and a live SSE stream of new events; it requires `TRACE_ENABLED` to also be on,
since there is nothing to show otherwise. `DASHBOARD_HOST` (default `0.0.0.0`, i.e. bind all interfaces
inside the container) and `DASHBOARD_PORT` (default `8080`) configure the dashboard's `ThreadingHTTPServer`;
`docker-compose.yml` publishes that port to the host bound to `127.0.0.1` only, so the dashboard stays local
to the machine even though the in-container bind is `0.0.0.0`. `TRACE_MAX_LIST_LIMIT` (default `100`) caps
how many traces the `GET` trace-list endpoint returns per request. See `## Agent Trace Dashboard` above for
what the dashboard shows and how it redacts secrets.

Never commit a real Telegram token.

## Quick Start

Make sure Ollama is running natively on the host — start `Ollama.app` on macOS, or run `ollama serve` — then
pull the configured model:

```bash
ollama pull qwen3:4b
```

Check that the model is installed:

```bash
ollama list
```

Start the bot:

```bash
docker compose up -d --build
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

The Telegram side is working, but inference failed. Ollama runs natively on the host, not in Docker, so
check it there instead of `docker compose logs`:

```bash
ollama list
ps aux | grep "[O]llama"
```

If the configured model is missing, pull it:

```bash
ollama pull qwen3:4b
```

If `.env` uses a different `OLLAMA_MODEL`, pull that exact model name. If `ollama list` itself fails to
connect, Ollama is not running — start `Ollama.app` (macOS) or run `ollama serve`.

### Ollama returns 404 for `/api/chat`

Most often this means the requested model is not pulled into the native Ollama installation:

```text
{"error":"model 'qwen3:4b' not found"}
```

Install it with `ollama pull <model-name>` on the host.

### Dashboard shows no traces

The dashboard loads but the trace list stays empty even after sending messages to the bot:

- Check that `TRACE_ENABLED` and `DASHBOARD_ENABLED` are both `true` (or unset — both default to `true`).
  A trace is only ever created when `TRACE_ENABLED` is on, and the dashboard has nothing to show if it was
  never on when the message came in.
- Check the container logs for the startup line confirming the dashboard actually started:

```bash
docker compose logs telegram-bot | grep "Dashboard listening on"
```

If that line is missing, the dashboard server never started for this run — recheck the two flags above and
restart the container.

### Can't reach http://localhost:8080

- Check `DASHBOARD_PORT` in `.env` — if it was changed from the default `8080`, use that port instead.
- Check the `ports:` publish in `docker-compose.yml` matches the port you're browsing to; it binds to
  `127.0.0.1` on the host, so the dashboard is reachable at `localhost`/`127.0.0.1` only, never from another
  machine on the network.
- Confirm the image was actually rebuilt after pulling in the dashboard code: `docker compose up -d --build
  telegram-bot`. Recreating the container without `--build` reuses the previously built image and can leave
  the dashboard server code (or the config change) out entirely — see `CLAUDE.md` for why this matters.

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
`docs/specifications/PROJECT_UNDERSTANDING_RU.md` for that vocabulary, used here as inspiration only, not a
target shape.

Before adding larger systems such as MCP, RAG, additional memory backends, or cloud deployment, read the
project notes in `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `Prompt.md`, and `docs/specifications/` (`Spec.md`,
`spec2.md`). Feature-level additions on top of `Spec.md` (typing indicator, chat allowlist, factual system
prompt) are documented in `docs/specs/2026-08-22-interactive-hardening.md`.
