# Technical Specification: Telegram AI Bot with Future-Ready Agent Boundaries

## 1. Objective

Build a Python 3.12+ Telegram AI Bot that receives text messages from Telegram, sends each message to a local LLM through Ollama, and replies to the same Telegram chat.

Related documentation:

- `README.md`: documentation map and recommended reading order.
- `Prompt.md`: Russian implementation prompt for a developer or AI coding agent.
- `Agent.md`: future Agent/Harness architecture notes, not current scope.
- `Cloud.md`: future cloud and deployment evolution notes, not current scope.

The current implementation must stay simple and stateless:

```text
User Message -> Telegram Adapter -> Application/Core -> Responder Interface -> Inference Provider -> Ollama -> Bot Reply
```

The implementation must not build a full Agent Harness, MCP integration, RAG system, memory layer, tool execution system, or autonomous agent loop now. It must establish clear architectural boundaries so these capabilities can be added later without rewriting the core bot flow.

## 2. Scope

### In Scope

- Python 3.12+ application.
- Direct Telegram Bot API integration over HTTP.
- Long polling through `getUpdates`.
- Reply delivery through `sendMessage`.
- Stateless message processing.
- Local inference through Ollama HTTP API.
- Replaceable inference contract, initially implemented by Ollama.
- Future-ready application boundary that can later call an Agent Service.
- Docker Compose with `telegram-bot` and `ollama`.
- Environment-based configuration.
- Non-root bot container.
- Minimal dependencies.
- Basic error handling, logging, and tests.

### Out of Scope

- Database.
- Redis.
- RAG implementation.
- Vector database.
- MCP server or MCP client implementation.
- Tool execution.
- Agent loop.
- Autonomous Agent Runtime / Harness implementation.
- Memory.
- Multi-agent orchestration.
- Web UI.
- Kubernetes.
- Separate Agent Service.
- PostgreSQL, Qdrant, MCP, or RAG containers.

## 3. Architecture

### 3.1 Current Runtime Architecture

```text
Telegram Bot API
       |
       v
Telegram Adapter
       |
       v
Application/Core
       |
       v
Responder / TextGenerator Interface
       |
       v
Ollama Inference Provider
       |
       v
Ollama HTTP API
       |
       v
Local LLM
```

The current responder is not a full autonomous agent. It has no agent loop, no tool calls, no permissions, no sandbox, and no memory. It is a simple stateless responder backed by an inference provider.

### 3.2 Dependency Rules

The dependency direction must remain stable:

```text
main -> telegram adapter + application/core + inference provider
telegram adapter -> application contract / internal DTOs
application/core -> responder or inference interface
inference/ollama -> Ollama HTTP API
```

Rules:

- Application/core must not import Telegram-specific modules.
- Application/core must not import Ollama-specific modules.
- Telegram adapter must not know Ollama request or response formats.
- Ollama provider must not know Telegram `chat_id`, `update_id`, or Telegram payloads.
- Provider-specific code must stay inside provider modules.

## 4. Suggested Project Structure

```text
app/
  main.py
  config.py
  telegram/
    __init__.py
    client.py
    updates.py
  application/
    __init__.py
    bot_service.py
    responder.py
  inference/
    __init__.py
    base.py
    ollama.py
tests/
  test_config.py
  test_telegram_updates.py
  test_inference_contract.py
Dockerfile
docker-compose.yml
.env.example
.gitignore
README.md
Agent.md
Cloud.md
```

Responsibilities:

- `app/main.py`: entry point, dependency construction, polling startup.
- `app/config.py`: environment parsing and validation.
- `app/telegram/client.py`: direct Telegram HTTP calls for `getUpdates` and `sendMessage`.
- `app/telegram/updates.py`: parsing Telegram updates into internal message objects.
- `app/application/bot_service.py`: message handling use case.
- `app/application/responder.py`: simple responder abstraction for current stateless replies.
- `app/inference/base.py`: minimal text generation contract.
- `app/inference/ollama.py`: Ollama HTTP provider.
- `tests/`: small unit tests for parsing, configuration, and contracts.

Future modules may be added later only when needed:

```text
app/agent/       # future Agent Runtime / Harness
app/tools/       # future Tool Registry and tool contracts
app/mcp/         # future MCP adapter/client layer
app/rag/         # future Knowledge/Retrieval service
app/memory/      # future Memory/State
app/sandbox/     # future isolated execution
app/telemetry/   # future traces, audit logs, metrics
```

Do not create complex empty subsystems in the initial implementation.

## 5. Functional Requirements

The bot must:

1. Poll Telegram using direct HTTP calls to `getUpdates`.
2. Extract `update_id`, `message.chat.id`, and `message.text`.
3. Ignore unsupported update types safely.
4. Keep an in-memory update offset during process runtime.
5. Avoid processing the same update more than once while the process is running.
6. Send each text message to the application/core boundary.
7. Generate a reply through the minimal responder/inference contract.
8. Send the reply through direct HTTP calls to `sendMessage`.
9. Continue polling after recoverable errors.

Persistent offset storage is not required.

## 6. Stateless Processing

The message contract is:

```text
input: one latest user text message
output: one generated reply
```

The application must not:

- store conversation history;
- maintain user sessions;
- pass prior messages to the model;
- implement memory;
- use a database for user messages;
- implement retrieval or RAG.

## 7. Inference Contract

The application must define a minimal contract equivalent to:

```python
class TextGenerator(Protocol):
    def generate(self, prompt: str) -> str:
        ...
```

or:

```python
generate(prompt: str) -> str
```

The current provider is Ollama. The architecture must allow adding vLLM later as another provider without changing Telegram polling, Telegram parsing, or application/core logic.

### 7.1 Ollama Provider

The Ollama provider must:

- communicate with Ollama over HTTP;
- use a configurable base URL;
- use a configurable model name;
- support non-streaming generation by default;
- return generated text as `str`;
- handle failed requests, timeouts, invalid JSON, unavailable models, and empty responses.

Example models:

- `qwen3:1.7b`;
- `tinyllama`.

Ollama is an independent process/container. It is not embedded into the bot process.

### 7.2 Future vLLM Provider

vLLM is not implemented now. The only requirement is that a later vLLM provider can implement the same text generation contract.

## 8. Configuration

Configuration must come from environment variables.

Required variables:

```text
TELEGRAM_BOT_TOKEN=replace_me
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:1.7b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=60
LOG_LEVEL=INFO
```

The repository must include:

- `.env.example` with placeholders only;
- `.gitignore` excluding `.env`, Python caches, virtual environments, and temporary files.

Secrets must never be hardcoded, committed, or logged.

## 9. Docker Requirements

Docker Compose must include only:

- `telegram-bot`;
- `ollama`.

The `telegram-bot` service must:

- run as a non-root user;
- read configuration from environment variables;
- call Ollama at `http://ollama:11434`;
- avoid privileged mode;
- avoid Docker socket mounts;
- avoid `~/.ssh` mounts;
- avoid broad host filesystem mounts;
- avoid storing secrets in the image.

Do not add PostgreSQL, Redis, Qdrant, MCP, RAG, or separate agent-service containers in the initial implementation.

## 10. Security Requirements

The implementation must:

- keep `TELEGRAM_BOT_TOKEN` only in environment variables;
- avoid logging secrets;
- use minimal third-party dependencies;
- avoid Telegram framework dependencies;
- run the bot container as non-root;
- avoid privileged containers;
- avoid Docker socket access;
- avoid broad host filesystem access;
- keep the runtime surface small.

Future security concepts must be documented but not implemented:

- Permission/Policy Engine for deciding whether actions are allowed.
- Sandbox executor for isolated execution.
- Audit trace for decisions, tool calls, and model requests.

## 11. Error Handling and Logging

Handle:

- Telegram API errors;
- Telegram network errors and timeouts;
- malformed Telegram responses;
- updates without text messages;
- Ollama API errors;
- Ollama network errors and timeouts;
- invalid JSON from Ollama;
- unavailable model;
- empty model response.

Logging should include enough context to debug issues without exposing tokens or secrets.

When inference fails, the bot should send a short user-facing error message instead of silently crashing.

## 12. Tests

Add minimal tests for:

- environment configuration parsing and validation;
- Telegram update parsing;
- the inference contract using a fake provider;
- application/core message handling with a fake responder/provider.

Unit tests must not require real Telegram or real Ollama.

## 13. Future Evolution / Architectural Path

The target architecture may evolve in this direction:

```text
Current bot
  -> separate Agent Service behind the same application boundary
  -> Agent Runtime / Harness with controlled loop
  -> Tool Registry and tool contracts
  -> Permission/Policy Engine
  -> Sandbox executor for isolated actions
  -> MCP adapter/client layer for standardized tools and context
  -> RAG/Knowledge service for retrieval
  -> Memory/State for longer-running tasks
  -> Telemetry/Trace for observability, token usage, decisions, tool calls
  -> multi-agent coordination only when a concrete need appears
```

Roles must remain distinct:

- RAG is the knowledge and retrieval subsystem.
- MCP is the standardized tool/context integration protocol.
- Harness is the control, orchestration, policy, and security layer.
- Tools are actions.
- Sandbox is execution isolation.
- Memory/State stores task state or longer-term experience.
- Telemetry/Trace records model calls, tool calls, decisions, errors, latency, and token usage.

The initial implementation must keep the application boundary stable so Telegram can later call either the local responder or a separate Agent Service without changing Telegram-specific code.

## 14. Acceptance Criteria

- The bot receives Telegram text messages through direct `getUpdates`.
- The bot sends replies through direct `sendMessage`.
- No Telegram framework library is used.
- Each message is processed independently and statelessly.
- No conversation history, sessions, database, memory, RAG, MCP, tools, or agent loop are implemented.
- Telegram adapter is separated from application/core.
- Application/core depends on a responder/inference contract, not on Ollama.
- Ollama provider implements the minimal `generate(prompt) -> str` contract.
- A future vLLM provider can be added without rewriting Telegram logic.
- Docker Compose includes only `telegram-bot` and `ollama`.
- The bot container runs as non-root.
- Docker Compose does not use privileged mode, Docker socket mounts, `~/.ssh` mounts, or broad host mounts.
- Configuration is loaded from environment variables.
- `.env.example` contains no real secrets.
- Errors and timeouts are handled and logged safely.
- Minimal tests cover config, Telegram parsing, and inference/application contracts.
- Future Harness/MCP/RAG evolution is documented clearly without implementing those systems now.

## 15. Definition of Done

- Python 3.12+ code is implemented.
- Direct Telegram long polling is implemented.
- Direct Telegram message sending is implemented.
- Ollama inference provider is implemented.
- Minimal responder/inference contract is implemented.
- Environment-based configuration is implemented and validated.
- `.env.example`, `.gitignore`, `Dockerfile`, `docker-compose.yml`, and `README.md` are included.
- No real tokens or secrets are present.
- No database, Redis, RAG, vector DB, MCP, tool execution, agent loop, memory, multi-agent system, web UI, Kubernetes, or separate agent service is included.
- The project can run locally with Docker Compose after `.env` is populated.
- The end-to-end flow works: `User Message -> Ollama -> Telegram Reply`.
- The code remains readable, small, and suitable for learning Python.

## 16. Interactive Hardening (Addendum)

The bot was extended with three additions on top of the boundaries in this spec, detailed in
`docs/specs/2026-08-22-interactive-hardening.md`:

- A native Telegram "typing..." chat action is kept alive (re-sent on an interval) while waiting for the
  Ollama reply, via `app/telegram/typing_indicator.py`. This lives in the Telegram adapter layer, not in
  `app/application/**`.
- An optional `ALLOWED_CHAT_ID` allowlist rejects messages from any other chat with a short reply, without
  calling the inference provider. The check lives in `app/main.py`'s polling loop, not in `BotService`.
- `TextGenerator.generate` gained an optional `system: str | None = None` parameter. `LLMResponder` passes a
  fixed, Russian, facts-only `SYSTEM_PROMPT` (`app/application/responder.py`) that instructs the model to
  say it does not know rather than guess. `OllamaProvider` forwards it as Ollama's native `system` field.

These additions do not change the stateless, single-message contract in §6, and do not add any new runtime
component beyond `telegram-bot` and `ollama` (`CLAUDE.md`).
