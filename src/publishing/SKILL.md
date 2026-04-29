---
name: daily-multi-platform-publisher
description: Use when the user wants to package a tech daily / AI daily report and its video into platform-specific publishing drafts for Telegram, 微信公众号, and B站, with optional delivery follow-through when the user explicitly asks to publish.
---

# Daily Multi Platform Publisher

Use this skill when the user wants `把科技日报发到 Telegram/微信公众号/B站`, `三平台分发`, or a reusable publishing skill for the daily-report workflow.

## Read First

1. Read [`references/platform-playbook.md`](references/platform-playbook.md) for platform-specific constraints.
2. Read [`references/publish-auth-matrix.md`](references/publish-auth-matrix.md) for the current Telegram / 微信公众号 / B站 strategy.
3. If the run is about WeChat Official Account live posting, also read [`references/wechat-oa-api-setup.md`](references/wechat-oa-api-setup.md).
4. If the run is about Bilibili live posting without Open Platform credentials, also read [`references/bilibili-browser-setup.md`](references/bilibili-browser-setup.md).
5. Confirm the source report exists.
6. If a video file already exists, pass it into the bundle generator so the output can reference the correct asset path.

## Default Mode

Default to **final bundle generation after video QA**. The bundle must reference the formal `final/video.mp4`; do not create a pre-video package.

```bash
python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-publish-bundle \
  --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/final/report.md \
  --out-dir /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/publish \
  --video-file /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/final/video.mp4 \
  --video-summary /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/build/video/build-summary.json \
  --cover-image /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/final-cover.png \
  --title-pack /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/publish/title-pack.json \
  --require-video
```

If the user wants the full post-report chain, run the three formal stages in order:

1. `python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-text-compile ...`
2. `python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-video-build ...`
3. `python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-publish-bundle ...`

## Active Platforms

Only produce deliverables for these platforms:

- **Telegram**: `telegram.txt` + `telegram-send.json`
- **微信公众号**: `wechat.docx` with inline images, plus a titled DOCX copy named `标题｜Lumi的AI速递｜YYYY-MM-DD.docx`
- **B站**: `bilibili.txt` + `bilibili-upload.json`
- **Title metadata**: `title-pack.json`

Do not produce: `xiaohongshu.md`, `zhihu.md`, `x-thread.txt`, `x-post.json`, `youtube.txt`, `youtube-upload.json`.

## Hard Requirements

- Final publish bundle keeps canonical files `telegram.txt`, `telegram-send.json`, `wechat.docx`, `bilibili.txt`, `bilibili-upload.json`, and `title-pack.json`; it may also include the titled DOCX copy from `title-pack.json`.
- The final video keeps canonical `final/video.mp4`; the pipeline also emits a titled MP4 copy named `标题【Lumi的AI速递第N期】.mp4`.
- `telegram-send.json.video_file` and `bilibili-upload.json.video_file` must both point to `final/video.mp4`; missing video is a hard failure.
- 微信公众号每条新闻至少要有 1 张真实来源图；没有图时 bundle 必须失败，不能生成兜底插画。
- 视频和微信都要共用同一套 item-level visual resolution，不允许各自偷偷降级。
- 标题、封面、视频和微信头条都必须服从同一条交叉确认后的头号热点。

## What This Skill Produces

- `telegram.txt`
- `telegram-send.json`
- `wechat.docx`
- `标题｜Lumi的AI速递｜YYYY-MM-DD.docx`
- `bilibili.txt`
- `bilibili-upload.json`
- `title-pack.json` is produced by the upstream title-pack stage and retained in `publish/`

## Live Posting Rules

- Telegram 默认仍然是 bundle handoff：
  - 先发封面图，
  - 再发正式 MP4，
  - 最后发 `telegram.txt`。
- Preferred Telegram live-send helper:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/scripts/send_telegram_bundle.py \
  --manifest /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/publish/telegram-send.json \
  --target <chat-id>
```

- 微信公众号默认继续走 `wechat.docx` 导入，不把 API 发布作为默认路径。
- B站优先 API only if Open Platform credentials truly exist; otherwise use browser fallback:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/scripts/bilibili_browser_bootstrap.py
```

- Only live-post when the user explicitly asks to publish now.
- Generate the draft bundle first even when live posting is requested.

## Writing Guardrails

- Telegram 保持紧凑，突出最热链接和当天判断。
- 微信公众号写成完整文章，不是视频描述改写版。
- B站简介要有栏目感，但不要堆原始链接。
- 三个平台共用同一事实核心，不额外发明故事。

## Output Contract

Always return:

- Result: success/failure
- Bundle directory: absolute path
- Draft files created: absolute paths
- WeChat docx: absolute path when generated
- Video file used: absolute path if provided
- Telegram delivery manifest: absolute path when generated
- Daily cover image: absolute path when resolved
- Any live-post blockers: only if the user asked for live posting
