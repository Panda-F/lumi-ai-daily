# Automation

Scheduler definitions copied from the live setup.

- `discovery-preflight/`: every two days, collect candidate news and source evidence with `gpt-5.4-mini`.
- `production-build/`: every two days, generate video, WeChat DOCX, and Bilibili artifacts from this repository.

Both automations run in this repository. Telegram delivery stays outside this repo.
