# Cloud and Deployment Notes

## Назначение

Этот файл описывает возможный cloud/deployment path для Telegram AI Bot. Он не является требованием к текущей локальной реализации.

Сейчас проект должен запускаться локально через Docker Compose:

```text
telegram-bot + ollama
```

Не нужно добавлять cloud infrastructure, Kubernetes, managed databases, vector databases, queues или отдельные agent services в первую реализацию.

## Текущий deployment target

Текущая цель:

```text
Developer machine
      |
      v
Docker Compose
      |
      +--> telegram-bot
      +--> ollama
```

Требования:

- bot container runs as non-root;
- no privileged mode;
- no Docker socket mount;
- no host root mount;
- no `~/.ssh` mount;
- secrets only through environment variables;
- Ollama runs as an independent process/container;
- Telegram bot calls Ollama through `http://ollama:11434`.

## Configuration and secrets

Secrets must stay outside images and source code.

Use environment variables:

```text
TELEGRAM_BOT_TOKEN=replace_me
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen3:1.7b
POLL_TIMEOUT_SECONDS=30
REQUEST_TIMEOUT_SECONDS=60
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

- Ollama in Docker Compose.

Later:

- Ollama on a GPU machine;
- vLLM on a GPU machine;
- managed model endpoint;
- separate inference network boundary.

The application/core should not depend on which option is used. It should depend on a text generation contract.

## Network model

Current local Compose network:

```text
telegram-bot -> ollama:11434
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

Do not implement now:

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
- sandbox worker pool;
- CI/CD pipeline.

## Current implementation rules

For the current bot:

- keep Docker Compose small;
- keep secrets in env;
- keep local inference separate from the bot process;
- keep code portable enough to move from local Docker Compose to a VM or container runtime later;
- document cloud evolution without implementing cloud infrastructure.

