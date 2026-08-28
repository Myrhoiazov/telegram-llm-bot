# Agent Instructions

This repository is an educational Telegram LLM bot. Preserve its core architecture:

- Telegram messages always enter through `BotService` and `AgentLoop`.
- The LLM decides whether to answer directly or call the single tool, `execute_command`.
- Do not add deterministic pre-LLM intent routers for skills such as email or weather.
- Skills live under `skills/<name>/SKILL.md`; the model discovers and reads them through
  `execute_command` (`ls skills/`, then `cat skills/<name>/SKILL.md`).
- Keep tool execution inside the existing `ExecTool` boundary unless a dedicated ADR/spec says otherwise.
- Telegram voice messages are preprocessed into text before `BotService`; they are not a second agent mode.
- Inline buttons are UI controls only: `New` starts a fresh conversation and resets input mode to text,
  while `Voice` stores voice input mode for the chat.

## Email Skill

The email skill is IMAP-based, not Gmail API based. It uses environment variables allowlisted by
`build_exec_env()` and helper scripts under `skills/email/scripts/`.

- Use `skills/email/SKILL.md` as the source of truth for user-facing email behavior.
- Use the scripts instead of large inline `python3 -c` snippets.
- Keep MIME header decoding in `skills/email/scripts/list_unread_headers.py` tested; user-visible output
  must not contain raw encoded headers such as `=?UTF-8?...?=`.
- The current IMAP skill can read unread messages and produce triage summaries. It cannot send mail,
  create Gmail drafts, or reliably edit Gmail labels.

## Development

- Prefer small, focused changes that match the current single-process harness.
- Add or update tests for behavior changes.
- Run the relevant pytest subset before reporting completion.
- Rebuild the Docker image after changing `app/`, `dashboard/`, or `skills/`, because these files are copied
  into the image rather than bind-mounted.
- Rebuild the Docker image after changing voice support: `ffmpeg` is installed in the image and Lemonade
  stays outside Docker, reachable through `STT_BASE_URL`.
- Never commit real secrets from `.env`.
- Do not add AI attribution trailers to commits.
