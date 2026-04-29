# Source Modules

The production code is grouped by responsibility rather than by its original OpenClaw folder names.

- `pipeline/`: orchestration, source archiving, text compile, QA, title/cover helpers, and command wrappers.
- `intelligence/`: editorial policy, source rules, high-signal feeds, templates, and style references.
- `media/`: story-image fetching, cover browser helpers, and Swift cover assembly.
- `video/`: Fish TTS, video script generation, Remotion renderer, and video style review.
- `publishing/`: Telegram, WeChat, and Bilibili packaging.
- `integrations/`: source and generation helpers that the main pipeline calls at the edge.

This snapshot is optimized for review. Before treating it as a runnable repo, audit and normalize the absolute paths listed in `../docs/absolute-paths.txt`.
