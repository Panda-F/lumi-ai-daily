# Bilibili Style Notes

Observed on **2026-03-29** against the two reference links the user provided:

- Reference A: [橘鸦Juya - BV1fbXHB4EEa](https://www.bilibili.com/video/BV1fbXHB4EEa/)
- Reference B: [小黛晨读 - BV1X3XjBeEh9](https://www.bilibili.com/video/BV1X3XjBeEh9/)

## What Matters Technically

- Reference A is reproducible as a **template news-card video**:
  - voiceover-led
  - mostly static editorial cards
  - source list in description
  - no talking-head dependency
- Reference B is a better **pacing constraint**:
  - fewer items feel more intentional
  - stronger column-style packaging
  - better fit for a `只保留 3-6 条精选` daily format

## Reproduction Strategy

Use a deterministic pipeline instead of a fully generative one:

1. Parse the Markdown daily report.
2. Keep only the best 3-6 items.
3. Fetch real source images from the linked pages when possible.
4. Render:
   - 1 intro cover
   - 6 item cards
5. Generate Chinese narration locally with macOS TTS.
6. Stitch audio + cards into a 16:9 MP4 with FFmpeg.
7. Emit sidecar subtitles and platform-publishing drafts.

## Style Guardrails

- Do not exceed 6 items unless the user explicitly asks.
- Fewer strong items beat a padded six-item list.
- Prioritize legibility over motion complexity.
- Keep the visuals editorial, not “AI wallpaper”.
- Treat motion as optional polish; the core product is the card hierarchy plus narration.
- Preserve the report’s selected-source discipline instead of turning the video into a loose commentary show.
- Do not sound like a TTS reading Markdown aloud.
- Each item should feel like a short **栏目点评**, not “标题 + 内容 + 解读” mechanically read out.
- The first sentence of each item should carry a **stance**:
  - what actually changed,
  - or why this is not just another launch.
- Aim for roughly **16-22 seconds per item**, not 28-35 seconds.
- If the source image is weak or mismatched, prefer a clean text-first card over a wrong image.
