# Cloud and Deployment Notes

## Назначение

Этот файл описывает возможный cloud/deployment path для Telegram AI Bot. Он не является требованием к текущей локальной реализации.

Сейчас проект должен запускаться локально: `telegram-bot` в Docker Compose, `ollama` — нативным процессом на хосте (macOS, `Ollama.app`/CLI):

```text
telegram-bot (Docker Compose) + ollama (native host process)
```

Причина: на macOS Docker Desktop не пробрасывает GPU/Metal в Linux-контейнеры, поэтому Ollama
в контейнере работает только на CPU и не укладывается в разумные тайминги даже для лёгких
моделей при загруженном хосте. Нативный `ollama serve` на macOS использует Metal-ускорение.

Не нужно добавлять cloud infrastructure, Kubernetes, managed databases, vector databases, queues или отдельные agent services в первую реализацию.

## Текущий deployment target

Текущая цель:

```text
Developer machine (macOS)
      |
      +--> Docker Compose --> telegram-bot
      |
      +--> native process   --> ollama (Metal-accelerated)
```

Требования:

- bot container runs as non-root;
- no privileged mode;
- no Docker socket mount;
- no host root mount;
- no `~/.ssh` mount;
- secrets only through environment variables;
- Ollama runs as an independent process on the host (not a container, on macOS — for Metal GPU access);
- Telegram bot calls Ollama through `http://host.docker.internal:11434`.

## Configuration and secrets

Secrets must stay outside images and source code.

Use environment variables:

```text
TELEGRAM_BOT_TOKEN=replace_me
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:4b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=180
LOG_LEVEL=INFO
```

For future cloud deployment, use a managed secrets mechanism:

- platform secret store;
- encrypted environment variables;
- CI/CD secret variables;
- runtime identity where available.

Do not commit real secrets.

## Local-first approach

The first implementation should remain local-first:

- local Telegram polling process;
- local Ollama inference;
- no public web server required;
- no inbound HTTP endpoint required;
- no webhook required;
- no cloud dependency required.

Long polling is enough for the current stage.

## Future cloud evolution

Possible path:

```text
Local Docker Compose
  -> single VM with Docker Compose
  -> managed container runtime
  -> separate Agent Service
  -> managed observability and secrets
  -> optional GPU inference host
  -> optional RAG/Knowledge service
  -> optional managed database/vector store
  -> Kubernetes only if operational complexity justifies it
```

This is an architectural path, not a current implementation checklist.

## Cloud components, later

Future cloud architecture may include:

```text
Telegram
  -> Bot Service
  -> Agent Service / Harness
  -> LLM Provider
  -> Tool/MCP Layer
  -> Permission/Policy Engine
  -> Sandbox Executor
  -> RAG/Knowledge Service
  -> Memory/State Store
  -> Telemetry/Trace Storage
```

Add each component only when there is a concrete need.

## Inference deployment options

Current:

- Ollama as a native host process on macOS (Metal-accelerated), reached from the
  `telegram-bot` container via `http://host.docker.internal:11434`. Not run in Docker
  Compose: Docker Desktop on macOS does not pass through GPU/Metal to Linux containers,
  which made CPU-only inference in a container too slow to be usable.

Later:

- Ollama on a dedicated GPU machine (Linux, real GPU passthrough);
- vLLM on a GPU machine;
- managed model endpoint;
- separate inference network boundary.

The application/core should not depend on which option is used. It should depend on a text generation contract.

## Network model

Current local network:

```text
telegram-bot (in Docker Compose) -> host.docker.internal:11434 -> ollama (native host process)
telegram-bot -> Telegram Bot API
```

Future cloud deployments should restrict network access:

- allow Telegram API;
- allow inference endpoint;
- allow approved internal services;
- deny broad access by default for sandboxed tool execution;
- never expose Docker socket or host internals.

## Observability, later

Future telemetry should capture:

- request id;
- update id;
- chat id hash or safe identifier;
- model name;
- latency;
- error type;
- token usage if available;
- agent step id when agent runtime exists;
- tool call and permission decisions when tools exist.

Do not log raw secrets or sensitive payloads.

## Cloud non-goals for current implementation

`tool execution`, `agent loop`, and `memory` are no longer non-goals: they are implemented locally,
in-process (`app/agent/`, `app/tools/`, `app/memory/`), which is what `docs/specifications/spec2.md` asked
for. The rest of the
list still applies. Do not implement now:

- Kubernetes;
- Terraform;
- cloud load balancer;
- managed database;
- Redis;
- vector database;
- queue;
- webhook receiver;
- public API;
- separate Agent Service;
- RAG service;
- MCP service;
- sandbox worker pool (documented next step: a dedicated exec-runner sidecar service holding the Docker
  socket — only that container, never telegram-bot — spinning up short-lived `--rm --network none`
  containers per `execute_command` call; see `docs/adr/0003-hardened-in-container-exec.md`);
- CI/CD pipeline.

## Current implementation rules

For the current bot:

- keep Docker Compose small;
- keep secrets in env;
- keep local inference separate from the bot process;
- keep code portable enough to move from local Docker Compose to a VM or container runtime later;
- document cloud evolution without implementing cloud infrastructure;
- after changing anything under `app/`, `skills/`, or the `Dockerfile`, rebuild the image before
  redeploying: `docker compose up -d --build telegram-bot` (or `docker compose build` first). Recreating the
  container alone — `docker compose up -d --force-recreate` without `--build` — reuses the last built image
  and silently keeps running old code; this has already caused a real incident where the bot ran a stale
  image for 5 days across several unrelated `.env` changes.

## `execute_command` runs in-process, not in a sandbox container

The `execute_command` tool (`app/tools/exec_tool.py`) runs as a subprocess inside the existing
`telegram-bot` container — not inside a separate sandboxed container. The container itself is the sandbox
boundary: non-root, non-privileged, no host mounts, no Docker socket. On top of that, the tool adds a fixed
non-source workspace `cwd`, a per-call timeout (`EXEC_TIMEOUT_SECONDS`), truncated stdout/stderr, and a
restricted environment allowlist instead of the bot process's full environment. That allowlist stops
*accidental* exposure of secrets like `TELEGRAM_BOT_TOKEN` (e.g. via a stray `env` command) — it is not a
hard isolation boundary, since `execute_command` still shares a container/process with the bot rather than
running in a separate sandboxed process. Genuine isolation is what the exec-runner sidecar (see
`docs/adr/0003-hardened-in-container-exec.md`) is for.

This is a deliberate scope decision for the current homework stage (per `docs/adr/0003-hardened-in-container-exec.md`),
not an oversight: a real Docker-backed sandbox would require a separate exec-runner sidecar service holding
the Docker socket, which is out of scope while `sandbox worker pool` remains a listed non-goal above. Do not
add that sidecar without first revisiting this non-goal.

