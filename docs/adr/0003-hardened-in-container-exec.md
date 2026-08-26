# Hardened in-container `exec`, not a Docker sandbox, for now

The `exec` tool lets the model run arbitrary shell commands, which is a real step up from the previously
stateless bot. We researched Docker's own "Docker Sandboxes" product and it turned out to be a CLI/microVM
tool for a human running an interactive coding agent on their own workstation — it has no documented
API/SDK a headless bot process could call per tool-call. A genuine sandbox would mean a separate
"exec-runner" sidecar service holding the Docker socket (only it, not the bot container) that spins up
short-lived `--rm --network none` containers per `exec` call. That is a real architectural option, but it
adds a new `docker-compose.yml` service and contradicts the current `CLAUDE.md`, which lists a sandbox
worker pool as an explicit non-goal — and it's more than a "minimal agent" (`spec2.md`'s own framing) needs.

Decision: for now, `exec` runs as a subprocess inside the bot's own container — already non-root,
non-privileged, no host mounts — with added hardening: a fixed non-source workspace `cwd`, a per-call
timeout, truncated stdout/stderr, and a restricted environment allowlist (see below) rather than the full
process environment. The container itself remains the sandbox boundary. The sidecar exec-runner is recorded
in `CLAUDE.md` as the next concrete step if/when real isolation is needed, not built now.

A related, smaller decision made at the same time: the `exec` subprocess does not inherit the bot's full
`os.environ`. It receives an explicit allowlist (`EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `EMAIL_ADDRESS`,
`EMAIL_APP_PASSWORD`, `PATH`) so an innocuous-looking model-issued command (e.g. plain `env`) does not
accidentally dump `TELEGRAM_BOT_TOKEN` or other bot secrets it has no reason to need. This is a hygiene
measure against accidental exposure, not a hard isolation boundary: `exec` still runs inside the same
container/process as the bot rather than a separate sandboxed process, so a sufficiently deliberate command
could still reach the parent process's environment (e.g. by reading `/proc/1/environ` on Linux, if the
container's PID namespace exposes it). Real isolation is exactly what the sidecar exec-runner described
above is for, once it's built.
