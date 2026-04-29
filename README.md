# Lumi AI Daily

[简体中文](README.zh-CN.md)

Lumi AI Daily is a review-ready snapshot of the AI Daily production pipeline: discovery, source archiving, editorial generation, title and cover strategy, narrated Remotion video, WeChat DOCX, Telegram bundle, and Bilibili metadata.

The tree is organized like a maintainable open-source repository so the workflow can be audited without digging through scheduler internals or historical generated artifacts.

> This is a review snapshot. The live scheduled jobs still execute production scripts from `/Users/dystopia/.openclaw/workspace`, so inspecting this folder will not affect the next automated run.

## Repository Map

```text
lumi-ai-daily/
├── automation/              # Codex cron definitions and task memory
├── src/
│   ├── pipeline/            # Orchestration, discovery, compilation, QA, wrappers
│   ├── intelligence/        # Source policy, writing rules, templates
│   ├── media/               # Story image resolution and cover assembly
│   ├── video/               # Fish TTS, video builder, Remotion template
│   ├── publishing/          # Telegram, WeChat DOCX, Bilibili bundle scripts
│   └── integrations/        # X reader, Tavily search, image generation helpers
├── config/                  # Runtime policy and style configuration
├── assets/                  # Shared BGM, Lumi assets, visual references
├── samples/                 # Lightweight 2026-04-28 run metadata
└── docs/                    # Architecture notes, source map, audit checklist
```

## Start Here

- Cron entrypoints:
  - `automation/discovery-preflight/automation.toml`
  - `automation/production-build/automation.toml`
- Pipeline orchestrator:
  - `src/pipeline/run_tech_daily_pipeline.py`
- Title and cover strategy:
  - `src/intelligence/references/title-cover-playbook.md`
  - `docs/research/title-cover-benchmark-2026-04-28.md`
- Discovery preflight:
  - `src/pipeline/tech_daily_prepare_discovery.py`
- Video builder:
  - `src/video/scripts/build_tech_daily_video.py`
  - `src/video/remotion/src/`
- Publishing:
  - `src/publishing/scripts/render_publish_bundle.py`
  - `src/pipeline/wechat_docx_builder.py`

## Pipeline Flow

1. `automation/discovery-preflight` runs the daily discovery preflight.
2. `src/pipeline/tech_daily_prepare_discovery.py` builds candidate pools and search terms.
3. `src/pipeline/tech_daily_text_compile.py` and `src/pipeline/ai_daily_llm_content.py` create the factual report and platform copy source.
4. `src/media/scripts/fetch_story_images.py` resolves item-level visual assets.
5. `src/pipeline/run_tech_daily_pipeline.py` prepares an imagegen cover brief, then coordinates cover, video, QA, and publish bundle stages.
6. `src/video/scripts/build_tech_daily_video.py` renders the Remotion video with Fish TTS.
7. `src/publishing/scripts/render_publish_bundle.py` creates Telegram, WeChat, and Bilibili artifacts.

## Documentation

- `docs/architecture.md`: module boundaries and data handoffs
- `docs/audit-checklist.md`: high-value review checklist
- `docs/source-map.md`: review paths mapped back to production source paths
- `docs/research/title-cover-benchmark-2026-04-28.md`: title and thumbnail benchmark examples
- `docs/absolute-paths.txt`: hard-coded absolute paths to inspect
- `docs/file-index.txt`: snapshot file inventory
- `docs/checksums.sha256`: snapshot checksums

## Snapshot Policy

Excluded on purpose:

- `node_modules/`
- Remotion `.bundle*` build caches
- historical `remotion/public/generated/` media
- `__pycache__/` and `*.pyc`
- full-size generated video/image/audio/DOCX artifacts

Included as lightweight evidence:

- `samples/2026-04-28/qa/`
- `samples/2026-04-28/build/video/*.json`
- `samples/2026-04-28/final/*.json|*.md|*.txt|*.srt`
- `samples/2026-04-28/publish/*.json|*.txt`
