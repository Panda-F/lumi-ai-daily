# Architecture

## System Boundary

The live workflow has two scheduled jobs:

- `automation/discovery-preflight`: collects and refreshes the daily candidate pool.
- `automation/production-build`: produces the full publication bundle without sending Telegram.

The review tree separates those entrypoints from reusable code under `src/`.

## Main Modules

### `src/pipeline`

Shared orchestration and validation scripts. The most important file is `run_tech_daily_pipeline.py`, which coordinates:

- discovery reuse and collection repair
- text compilation
- cover copy and title pack generation
- imagegen cover brief generation, cover assembly/fallback, and cover review
- video build and style review
- publish bundle creation
- final artifact consistency checks

### `src/intelligence`

Editorial policy, source playbooks, high-signal source lists, writing templates, and title/cover strategy references for the AI Daily report.

### `src/media`

Image acquisition and cover production. The preferred path prepares a prompt brief for the system imagegen skill; Swift-based magazine-cover rendering remains a deterministic fallback and layout-debug tool.

### `src/video`

Narrated video production. The Python builder prepares script, voice, media, subtitles, and Remotion manifests; the Remotion project renders the final template.

Key review targets:

- `scripts/build_tech_daily_video.py`
- `scripts/video_build_script.py`
- `scripts/video_style_review.py`
- `remotion/src/ItemScene.tsx`
- `remotion/src/DailyReport.tsx`
- `remotion/src/TextFit.tsx`

### `src/publishing`

Platform packaging for Telegram, WeChat DOCX, and Bilibili. The WeChat DOCX renderer itself lives in `src/pipeline/wechat_docx_builder.py` because it is shared by the publishing wrapper.

### `src/integrations`

External-source helpers:

- `x-reader` for X/Twitter posts
- `tavily-search` for web search support
- `openai-image-gen` for image generation support

## Data Handoff

```text
discovery/*.json
  -> source-pack/ and reference-pack/
  -> final/report.md + final/report.json + final/content-manifest.json
  -> assets/story/manifest.json
  -> cover-lab/imagegen-cover-brief.md/json
  -> cover-lab/final-cover.png
  -> build/video/build-summary.json + build/video/video.mp4
  -> publish/telegram-send.json + publish/wechat.docx + publish/bilibili-upload.json
```

The sample data under `samples/2026-04-28/` keeps the JSON/Markdown/TXT/SRT side of that handoff visible without carrying large binary artifacts.
