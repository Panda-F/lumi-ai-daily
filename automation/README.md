# Automation

Codex cron job definitions copied from the live scheduler.

- `discovery-preflight/`: daily candidate discovery and preflight collection.
- `production-build/`: full daily artifact generation, excluding Telegram send.

Both copied automations currently use `gpt-5.5`, high reasoning, and the Desktop AI Daily reports directory as `cwd`.
