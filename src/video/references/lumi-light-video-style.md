# Lumi Light Video Style

Use this reference when the daily-video build should match the `light` HTML baseline:

- Intro baseline: `lumi-intro-light.html`
- Item baseline: `lumi-item-light.html`

## Target Spec

- `1920x1080`
- `16:9`
- `60fps`
- Warm light editorial layout with Lumi pink branding
- Default narration voice: `female_student`
- Subtitle mode: `sentence_bar`
- Subtitle presentation: single-line gray bar, centered at the bottom safe area

## Intro Layout

- Left `46%` / right `54%`
- Left side:
  - Lumi circular media area (must use `lumi-dance.gif` — animated GIF, not static image)
  - GIF asset path: `/Users/dystopia/.openclaw/workspace/assets/lumi-dance.gif`
  - dashed outer ring
  - scan line
  - floating particles
  - gradient Lumi badge
- Right side:
  - top-right brand pill + date / issue
  - `DAILY BRIEFING · 早安`
  - `早上好` plus sun icon
  - shimmer divider
  - trend tags
  - agenda summary card
  - opening / transition card
  - issue slogan uses a Chinese version of a real famous quote with an author, not a generic Lumi sentence
- Bottom:
  - frosted status bar

## Item Layout

- Top bar:
  - 58px brand header
  - 40px category tabs
- Main:
  - left `46%`, right `54%`
  - left column:
    - 44px topic icon
    - 46px heavy headline
    - gradient underline
    - information cards with one strong heading and 2-3 short bullet-like points when useful
    - varied role icons for creative, compliance, research, tooling, cost, evaluation, risk, and workflow
  - right column:
    - source line
    - quote-dominant block
    - optional clean media card above quote
    - Lumi mini avatar
- Bottom:
  - 44px global item rail
  - 52px dark subtitle/title bar

## Copy Rules

- `display_title` keeps product/source naming for on-screen display.
- `spoken_title` and subtitles use Chinese-friendly spoken aliases where needed.
- Keep English quote text only in quote blocks; do not read long English sentences directly in narration.
- Intro target duration: `15-20s`.

## Media Rules

- **Every item MUST have at least 2 media assets.** No exceptions. No blank slides.
- Prefer clean promo art, product images, GIFs, or illustrations.
- If the local manifest does not have enough clean media, run broadened web search fallback (up to 4 extra candidates).
- Semantic relevance beats generic prettiness: only use search fallback when the result title, source page, official domain, or image URL clearly matches the current spoken point.
- Hard-reject: paper PDFs, arxiv screenshots, browser UI captures, text-heavy scorecards.
- Reject generic article header photos and decorative meta images unless the image itself is directly about the story.
- No full-screen webpage screenshots.
- The preferred rhythm is: card page first, then 1-2 dedicated media pages.
- When no clean media exists after all fallbacks, use gradient fallback artwork cards (icon + title), never leave a blank white area.
- Internal labels like "配图 X/Y" must never appear in the final rendered video.

## Audio Rules

- BGM: `/Users/dystopia/.openclaw/workspace/assets/bgm-lofi-morning.mp3`
- BGM plays only during intro and outro scenes, with 1.5s (90 frame) smooth fade transitions.
- BGM is silent during all item narration scenes.
- Slogan: "看懂变化，少走弯路" (not "AI在变，判断先行").

## Validation Rules

- Build output is not reviewable unless the same output directory contains:
  - `mp4`
  - `srt`
  - `slides/*`
  - `remotion-manifest.json`
  - `video-review.json`
  - `build-summary.json`
- Run HTML baseline screenshot checks against the light HTML files.
- Style review should inspect:
  - intro still
  - item still
  - one strong-media still
  - one no-media still
- Alignment review should fail if:
  - subtitle lead is earlier than `120ms`
  - subtitle tail is later than `180ms`
  - any cue exceeds the supported sentence-bar width budget
