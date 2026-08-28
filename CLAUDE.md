# Cloud and Deployment Notes

@AGENTS.md

- Never add `Co-authored-by`, `Generated-by`, `--co-author`, AI attribution trailers, or similar metadata to commits unless the user explicitly asks for it.

## Current Target

This project is local-first:

```text
telegram-bot (Docker Compose)
  -> Ollama on the host at OLLAMA_BASE_URL
  -> Lemonade STT on the host at STT_BASE_URL
```

Ollama and Lemonade run outside Docker on macOS so they can use host acceleration and local model storage.
The bot container calls them through `host.docker.internal`.

## Non-Goals

Do not add cloud infrastructure for the current stage:

- Kubernetes, Terraform, managed databases, Redis, queues, vector stores, webhooks, public APIs, or a
  separate Agent Service;
- Docker socket mounts or privileged containers;
- a separate sandbox worker pool, unless the existing exec-runner ADR/non-goal is explicitly revisited.

## Local Surfaces

Allowed local HTTP surfaces:

- Telegram outbound API calls;
- Ollama `/api/chat` through `OLLAMA_BASE_URL`;
- Lemonade `/v1/audio/transcriptions` through `STT_BASE_URL`;
- dashboard on localhost, published by Compose as `127.0.0.1:${DASHBOARD_PORT}`.

Do not expose the dashboard, Ollama, or Lemonade publicly without a new deployment decision.

## Rebuild Rule

The image copies `app/`, `skills/`, and `dashboard/`. After changing any of those files, or after changing
the `Dockerfile` system dependencies such as `ffmpeg`, rebuild before redeploying:

```bash
docker compose up -d --build
```
