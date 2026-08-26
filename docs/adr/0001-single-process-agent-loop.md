# Single-process agent loop; ManBot's multi-process shape deferred to a separate repo

The bot is evolving from a stateless one-shot responder into a minimal autonomous agent (harness + `exec`
tool + SQLite memory) for the `docs/specifications/spec2.md` homework.
`docs/specifications/PROJECT_UNDERSTANDING_RU.md` documents ManBot, a
multi-process, JSONL-message-passing architecture (separate Orchestrator/Planner/Executor/Services
processes) as an aspirational reference. We deliberately do not adopt that shape here: the harness stays
one Python process with internal module boundaries (`app/agent/`, `app/tools/`, `app/memory/`) that could
be split into processes later, and any genuine multi-process ManBot-style system is built in a separate
future repository, not grown inside this one. This keeps `docker-compose.yml` at `telegram-bot` + `ollama`
and the homework scope achievable, while the module boundaries are shaped so a future split doesn't require
a rewrite.
