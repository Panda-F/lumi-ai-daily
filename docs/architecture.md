# Architecture

## Boundary

The repo keeps the daily AI report path narrow:

- `automation/discovery-preflight`: collect fresh candidates, source packs, reference packs, and story visuals.
- `automation/production-build`: consume the collected day and produce video, WeChat DOCX, and Bilibili metadata.
- Review-facing daily output folders are `01-原始信息/`, `02-文字产出物/`, and `03-视频相关/`; `process/` remains the machine-readable build workspace.

There is no auto-publish path in this repo.

## Modules

### `src/run_tech_daily_pipeline.py`

Owns the daily orchestration path. It calls discovery reuse, report building, text compile, cover brief preparation, video build, WeChat DOCX rendering, and Bilibili metadata rendering.

### `src/common`

Shared paths, report parsing, source URL normalization, title cleanup, and compact label helpers.

### `src/discovery`

Owns source discovery, RSSHub and early-signal collection, search term expansion, source/reference archiving, Tavily search, and X reader support. This layer collects real story images and source evidence; it does not generate cover art.

### `src/content`

Owns factual report generation, content compilation, LLM writing policy, WeChat article assembly, WeChat DOCX rendering, and title/cover copy text. WeChat publishing files live here because they are text/document products.

### `src/visuals`

Owns the cover brief and cover resolution boundary. The actual cover bitmap is generated through the imagegen skill; story images are collected from official, media, paper, product, or network sources.

### `src/video`

Owns video script payloads, Fish TTS runtime, BGM analysis, the Python video builder, and Bilibili text/upload manifest generation.

### `src/video/remotion`

Contains the Remotion app, Remotion components, and `.mjs` render/demo scripts. This is the one intentional nested implementation folder.

### `src/intelligence`

Owns one unified source policy in `source_policy.toml`, plus writing methodology, title/cover playbook, report template, and writing profile.

## Data Handoff

```text
process/discovery/*.json
  -> process/source-pack/ and process/reference-pack/
  -> process/report.md + process/report.json + process/content-manifest.json
  -> process/cover/imagegen-cover-brief.md/json
  -> final/cover.png
  -> process/video/build-summary.json
  -> final/<title>｜Lumi的AI速递｜YYYY-MM-DD.mp4 + final/video.srt
  -> final/<title>｜Lumi的AI速递｜YYYY-MM-DD.docx
  -> final/bilibili.txt + final/bilibili-upload.json
```

Story images are collected with source/reference packs. If a selected story has no usable real image, the WeChat DOCX step fails instead of making filler art.
