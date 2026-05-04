# Lumi AI Daily

[简体中文](README.zh-CN.md)

Lumi AI Daily is the reviewable source tree for the daily AI news workflow. It keeps the production path focused on three jobs: find fresh high-signal stories and their real visuals, write the WeChat/Bilibili/video copy, and render the Remotion video plus WeChat DOCX and Bilibili metadata.

## Repository Map

```text
lumi-ai-daily/
├── automation/              # Daily cron definitions
├── src/
│   ├── run_tech_daily_pipeline.py
│   ├── common/              # Shared paths, report model, source/title utilities
│   ├── discovery/           # News/source discovery and real story image collection
│   ├── content/             # Fact report, content manifest, WeChat DOCX
│   ├── visuals/             # Cover brief for the imagegen skill
│   ├── video/               # Video script, TTS, BGM, Bilibili metadata
│   ├── video/remotion/      # Remotion app and render scripts
│   └── intelligence/        # One source policy file plus writing/title/cover guidance
├── config/                  # Runtime style policy
├── assets/                  # BGM, Lumi identity assets, visual references
└── docs/                    # Architecture and file inventory
```

## Main Entry Points

- `automation/discovery-preflight/automation.toml`
- `automation/production-build/automation.toml`
- `src/run_tech_daily_pipeline.py`
- `src/intelligence/source_policy.toml`
- `src/discovery/prepare_discovery.py`
- `src/content/compile_content.py`
- `src/content/render_wechat.py`
- `src/visuals/prepare_cover_brief.py`
- `src/video/build_video.py`
- `src/video/render_bilibili.py`

## Pipeline Flow

1. `discovery/prepare_discovery.py` collects current AI stories and search terms from `src/intelligence/source_policy.toml`.
2. `content/build_report.py` creates the factual report when daily report inputs are missing.
3. `content/compile_content.py` and `content/llm_content.py` generate the article, video copy, title pack, and Bilibili copy.
4. Story images come from the same source/reference packs created during collection; missing item images fail the WeChat DOCX step instead of creating local filler art.
5. `visuals/prepare_cover_brief.py` prepares the cover brief, then the cover must be generated through the imagegen skill.
6. `video/build_video.py` renders the Remotion video with Fish TTS.
7. `content/render_wechat.py` writes the WeChat DOCX; `video/render_bilibili.py` writes the Bilibili files.

Daily outputs use only two top-level artifact folders: `process/` for intermediate materials and `final/` for title-named video, cover, one DOCX, subtitles, and Bilibili metadata.

## Documentation

- `docs/architecture.md`: current module boundaries and data flow
- `docs/code-file-index.tsv`: code file list with Chinese notes
- `docs/file-index.txt`: repository file inventory
- `docs/checksums.sha256`: current checksums
