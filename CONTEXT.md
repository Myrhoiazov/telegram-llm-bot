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

**exec tool**:
The single tool exposed to the model via Ollama's native tool-calling. Runs a shell command inside the bot
container, with a timeout and truncated output, cwd fixed to a dedicated workspace directory. The container
itself (non-root, non-privileged, no host mounts) is the sandbox boundary — no additional command allow-list
or policy engine.

**Skill**:
A markdown file under `skills/` that documents either how to use one CLI/API (Type A) or a multi-step routine
(Type B). Not preloaded into the system prompt — the model discovers and reads skills on demand via the
`exec` tool itself (`ls skills/`, `cat skills/<name>.md`), so the tool surface stays at exactly one tool.
