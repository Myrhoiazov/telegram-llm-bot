# One tool (`exec`) via native Ollama tool-calling; skills self-loaded through it

`spec2.md` requires one universal tool. We considered hand-rolling a text-based ReAct-style protocol
(model emits `ACTION: ...` text the harness parses) versus using Ollama's native tool-calling. `ollama show
qwen3:1.7b` confirms the model advertises a `tools` capability, so the harness sends `exec` as a real
function-calling tool via `/api/chat` and reads back structured `tool_calls`, instead of parsing free-form
text. This is more robust (no fragile output parsing) and matches how the model was actually trained.

We also considered giving skills their own `read_skill`/`list_skills` tool. Instead, skill `.md` files live
under `skills/` and the system prompt tells the model it can discover and read them itself via `exec`
(`ls skills/`, `cat skills/<name>.md`). This keeps the tool surface at exactly one tool as the assignment
asks, at the cost of the model needing an extra `exec` round-trip to read a skill before acting on it.

## Naming the registered function: `execute_command`, not `exec`

We call this "the `exec` tool" throughout this and other docs, but the function name actually registered
with Ollama's native tool-calling is `execute_command`. This is not a style choice: we tested the locally
installed `qwen3:1.7b` against `/api/chat` with the tool literally named `exec` (and separately `shell`,
`terminal`), and in every case, across repeated deterministic trials at `temperature: 0`, the model silently
produced no `tool_calls` at all — empty content, no call, no error. Renaming the exact same tool definition
to `execute_command` (or `run_shell_command`) made the model call it reliably on the same prompts. We did
not dig into why `qwen3:1.7b` behaves this way; the finding is purely empirical, reproduced against the
model we're actually running. Practical consequence: `ExecTool.name` (`app/tools/exec_tool.py`) and the
schema sent to Ollama use `execute_command`; do not rename it back to `exec` without re-verifying against
the target model first.
