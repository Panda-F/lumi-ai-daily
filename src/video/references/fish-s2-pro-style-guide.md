# Fish S2 Pro Style Guide

Use this when the video build is calling a remote Fish `S2 Pro` endpoint.

Official Fish docs say `S2` / `S2 Pro` supports inline natural-language bracket tags. The safest documented examples are:

- `[whisper]`
- `[laugh]`
- `[emphasis]`
- `[sigh]`
- `[gasp]`
- `[pause]`
- `[angry]`
- `[excited]`
- `[sad]`
- `[surprised]`
- `[inhale]`
- `[exhale]`

Official sources:

- https://docs.fish.audio/developer-guide/models-pricing/models-overview
- https://docs.fish.audio/changelog

## Recommended Video Presets

- `news` -> `[emphasis] [pause]`
- `bright` -> `[excited] [emphasis]`
- `gentle` -> `[pause] [exhale]`
- `serious` -> `[pause] [emphasis]`

## Guardrails

- For a news video, default to `news` or `serious`, not `playful`.
- Use 1-2 tags, not a whole chain.
- Let the script carry the structure; tags should only shape vocal delivery.
