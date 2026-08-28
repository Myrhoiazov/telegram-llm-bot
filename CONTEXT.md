# Telegram AI Bot

A local-first Telegram bot backed by Ollama, evolving from a stateless one-shot responder into a minimal
autonomous agent (harness + tool use + memory) inside a single process. Multi-process ManBot-style evolution
is explicitly out of scope for this repo — see `docs/specifications/PROJECT_UNDERSTANDING_RU.md` for that vocabulary, applied
here as inspiration only.

## Language

**Harness (Agent Loop)**:
The code that repeatedly calls the model, dispatches any tool calls it requests, and feeds results back,
until the model returns a final answer or a max-step guard trips. Lives in `app/agent/`. Replaces the old
one-shot `LLMResponder` entirely — it is not an optional second mode.
_Avoid_: Orchestrator, Planner, Executor (ManBot's heavier multi-process roles — this project collapses them
into one loop, not separate components).

**Conversation**:
One bounded run of chat history stored in SQLite, scoped to a chat_id. `/new` closes the current conversation
and opens a fresh one; it does not delete history, just starts a new boundary the harness reads from.
_Avoid_: Session, chat (see Chat below).

**Chat**:
The Telegram chat itself, identified by `chat_id`. A chat has a sequence of conversations over time.

**Input Mode**:
A per-chat setting stored in SQLite (`chat_settings.input_mode`). `text` is the default. The `Voice` inline
button sets it to `voice`; `/new` and the `New` inline button reset it to `text`. Input mode is UI state, not
an alternate harness or a separate memory boundary.

**Update Event**:
The internal representation returned by `parse_updates`: `TextMessage`, `VoiceMessage`, or `CallbackQuery`.
Telegram payload parsing stops at this boundary so `main.py` can route text, voice, and button callbacks
without leaking raw Telegram JSON through the application.

**Voice Input**:
A Telegram `voice` message that is downloaded via `getFile`/file API, converted from OGG/Opus to 16 kHz mono
WAV with `ffmpeg`, transcribed by the STT provider, and then passed to `BotService` as plain text. Voice input
does not bypass the LLM and does not create a separate conversation.

**STT Provider**:
The speech-to-text service used before text enters the harness. Current provider: Lemonade's
OpenAI-compatible `/v1/audio/transcriptions` API, reached through `STT_BASE_URL`. It runs outside Docker on
the host by default, like Ollama.

**exec tool**:
The single tool exposed to the model via Ollama's native tool-calling. Runs a shell command inside the bot
container, with a timeout and truncated output, cwd fixed to a dedicated workspace directory. The container
itself (non-root, non-privileged, no host mounts) is the sandbox boundary — no additional command allow-list
or policy engine.

**Skill**:
A markdown file under `skills/` that documents either how to use one CLI/API (Type A) or a multi-step routine
(Type B). Not preloaded into the system prompt — the model discovers and reads skills on demand via the
`execute_command` tool itself (`ls skills/`, `cat skills/<name>/SKILL.md`), so the tool surface stays at
exactly one tool.

**Trace**:
One record of a single Telegram message's full trip through the harness, from `AgentLoop.handle_message` to
its reply. Lifecycle: `RUNNING` -> `COMPLETED` / `FAILED` / `MAX_STEPS_REACHED`. Created by the Tracer, persisted
by the Trace Store, viewed in the Dashboard.
_Avoid_: Run, Request (too generic; Trace is the one bounded, lifecycle-tracked unit).

**Agent Event**:
A structured, timestamped, sequenced record of one observable harness action within a Trace (e.g. an LLM call
starting, a tool call completing). Ordered by a per-trace sequence number, not wall-clock time.

**Tracer**:
The component that creates Traces and emits Agent Events: `AgentTracer` (real implementation) or `NullTracer`
(no-op used when tracing is disabled). Tolerates its own failures — a broken Tracer must never break message
handling, so every Tracer method swallows its own exceptions.

**Trace Store**:
SQLite persistence for Traces and Agent Events (`app/telemetry/store.py`). Separate tables from conversation
memory, but the same database file as `ConversationStore` (`MEMORY_DB_PATH`).

**Dashboard**:
The local-only web UI (`app/dashboard/`) for viewing Traces live (via SSE) and historically. Bound to
`127.0.0.1` by default; not a public API, not a webhook receiver.
