# telegram-llm-bot

`telegram-llm-bot` is a small educational Python 3.12+ project: a stateless Telegram bot that sends each incoming text message to a local LLM through Ollama and replies with the generated answer.

The project intentionally keeps the first version simple:

```text
User Message -> Telegram Bot API -> Python Application -> Ollama -> Local LLM -> Bot Reply
```

No dialogue history, database, Redis, RAG, memory, agent loop, tools, web UI, or Kubernetes are used.

## Concept

The bot treats every Telegram message as an independent request:

```text
input: one latest text message
output: one generated reply
```

This keeps the code easy to study and easy to extend later. Telegram integration, application logic, and inference are separated so another inference provider, such as vLLM, can be added without rewriting Telegram polling.

## Features

- Direct Telegram Bot API integration over HTTP.
- Long polling with `getUpdates`.
- Replies with `sendMessage`.
- In-memory Telegram update offset during process runtime.
- Stateless LLM calls through a `generate(prompt) -> str` contract.
- Ollama HTTP provider using `/api/generate`.
- Docker Compose with `telegram-bot` and `ollama` services.
- Environment-based configuration.
- Non-root bot container.
- Basic logging, error handling, and tests.

## Project Layout

```text
app/
  main.py                    # entry point and dependency wiring
  config.py                  # environment parsing and validation
  telegram/
    client.py                # Telegram HTTP API client
    updates.py               # update parsing and offset handling
  application/
    bot_service.py           # message handling use case
    responder.py             # stateless responder abstraction
  inference/
    base.py                  # TextGenerator contract
    ollama.py                # Ollama provider
tests/                       # pytest test suite
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
```

`docker-compose.yml` sets `OLLAMA_BASE_URL` to `http://ollama:11434` for the bot container.

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

### Ollama returns 404 for `/api/generate`

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

The code is shaped so the inference layer can be replaced later:

```text
Telegram layer -> BotService -> Responder -> TextGenerator -> OllamaProvider
```

A future vLLM provider or separate Agent Service should implement the same text generation boundary while keeping Telegram polling and message handling unchanged.

Before adding larger systems such as MCP, RAG, memory, tools, or cloud deployment, read the project notes in `AGENTS.md`, `CLAUDE.md`, `Prompt.md`, and `Spec.md`.
