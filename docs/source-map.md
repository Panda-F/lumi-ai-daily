# Source Map

This review snapshot keeps production provenance explicit. Use this map when comparing the reorganized tree with the live workspace files.

## Automations

- `/Users/dystopia/.codex/automations/ai-codex/` -> `automation/discovery-preflight/`
- `/Users/dystopia/.codex/automations/ai-codex-2/` -> `automation/production-build/`

## Pipeline

- `/Users/dystopia/.openclaw/workspace/scripts/` -> `src/pipeline/`

## Domain Modules

- `/Users/dystopia/.openclaw/workspace/skills/ai-daily-intel/` -> `src/intelligence/`
- `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/` -> `src/media/`
- `/Users/dystopia/.openclaw/workspace/skills/tech-daily-video-factory/` -> `src/video/`
- `/Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/` -> `src/publishing/`

## Integrations

- `/Users/dystopia/.openclaw/workspace/skills/x-reader-skill/` -> `src/integrations/x-reader/`
- `/Users/dystopia/.openclaw/workspace/skills/openclaw-tavily-search/` -> `src/integrations/tavily-search/`
- `/Users/dystopia/.openclaw/workspace/skills/openai-image-gen/` -> `src/integrations/openai-image-gen/`

## Runtime Support

- `/Users/dystopia/.openclaw/workspace/config/` -> `config/`
- `/Users/dystopia/.openclaw/workspace/assets/` -> `assets/`
- `/Users/dystopia/.codex/skills/.system/imagegen/` -> runtime cover generation skill, referenced but not vendored

## Samples And Reports

- `/Users/dystopia/Desktop/AI-Daily-Reports/2026-04-28/` metadata only -> `samples/2026-04-28/`
- `/Users/dystopia/.openclaw/workspace/reports/ai-daily-report-generation-system-analysis-2026-04-24.md` -> `docs/legacy-system-analysis-2026-04-24.md`
