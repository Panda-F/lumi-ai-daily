---
name: tech-daily-video-factory
description: Use when the user wants to turn a tech daily / AI daily Markdown report into a reproducible 16:9 narrated video with a Remotion render pipeline, Fish-first narration, and compatibility outputs for downstream publishing.
---

# Tech Daily Video Factory

Use this skill when the user wants `科技日报视频版`, `AI 早报视频`, a Bilibili-style curated recap with at most `6 条精选`, or a reproducible local pipeline for turning the daily report into a narrated MP4.

## Read First

1. Read [`references/bilibili-style-notes.md`](references/bilibili-style-notes.md) for the reference-video breakdown and the exact style target.
2. Read [`references/lumi-light-video-style.md`](references/lumi-light-video-style.md) for the active `light` HTML baseline and validation rules.
3. If remote Fish TTS is in play, also read [`references/fish-s2-pro-style-guide.md`](references/fish-s2-pro-style-guide.md).
4. Confirm the source report already exists and follows the `ai-daily-intel` curated-item structure.
5. If the user also wants cross-post copy, use `/Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/SKILL.md` after the video is built.

## What This Skill Produces

- A local 16:9 `.mp4` daily-video draft, defaulting to the current `1920x1080 / 60fps` Remotion pipeline in this workspace
- HTML-baseline comparison screenshots for the active light style
- One intro cover image for the video still pipeline
- One still image per scene for review and publishing
- Narration audio files
- A sidecar `.srt`
- A `remotion-manifest.json`
- A `video-script.json`
- A `video-review.json`
- A `timeline.json`
- A `build-summary.json` with paths, durations, frame ranges, source mapping, style review, and alignment review
- A `media_alignment_review` block in `build-summary.json` for per-item image/script relevance

## Default Video Style

- Up to **6 selected items**
- `1920x1080 / 60fps / 16:9`
- Warm editorial layout with **Lumi light pink** branding
- One intro + one scene per selected item + short outro
- Default remote narration reference: `female_student`
- Sentence-bar subtitles, forced to a single line in the bottom gray bar
- Each news item should land with at least **2 usable images** in the final scene data
- Builds should fail fast when any news item cannot keep **2 reviewed images**
- Reuse real story images first; if a story is missing media, automatically search the web for representative images before falling back
- Search fallback must stay semantically tied to the spoken story; reject generic lead photos, lifestyle headers, and unrelated meta images even if they look nicer
- Every selected image should also pass a semantic alignment review against the news item and oral script
- The visual baseline is `lumi-intro-light.html` + `lumi-item-light.html`
- No full-screen webpage screenshot backgrounds

## Optional Remote TTS

- This skill uses a user-owned remote TTS endpoint such as Fish Audio `S2 Pro` as the default narration path.
- Treat local `say` as the **resilience fallback**:
  - if the Fish request succeeds, use the returned audio,
  - if it fails, times out, or returns invalid audio, fall back to local narration,
  - do not let remote TTS failure break the main video build.
- Current supported contract in this workspace:
- Fish style control can be added with `--tts-style-preset` or direct `--tts-style-tags`.

```bash
python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-video-build \
  --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md \
  --out-dir /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/build/video \
  --tts-endpoint http://192.168.1.13:8888/v1/tts \
  --tts-reference-id female_student \
  --tts-style-preset news
```

## Workflow

1. Start from an existing report such as `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md`.
2. Build the video with:

```bash
python3 /Users/dystopia/.openclaw/workspace/scripts/tech-daily-video-build \
  --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/final/report.md \
  --out-dir /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/build/video \
  --tts-reference-id female_student \
  --tts-style-preset news
```

3. Optional knobs:
   - `--max-items 6` to cap the reference format
   - `--manifest /abs/path/to/manifest.json` if story images were already fetched elsewhere
   - `--tts-endpoint http://192.168.1.13:8888/v1/tts` to try remote TTS first
   - `--tts-reference-id female_student` to pick the configured default Lumi voice
   - `--tts-style-preset news` to make Fish read more like an anchor voice
   - `--tts-style-tags "[emphasis] [pause]"` for direct Fish inline control
   - `--tts-timeout 45` to cap remote TTS wait time before falling back
   - `--voice Tingting` for the fallback macOS voice
   - `--rate 220` to speed up fallback narration slightly
   - `--lumi-intro-image /abs/path/to/lumi.jpeg` to override the intro portrait
   - `--lumi-avatar-image /abs/path/to/lumi.png` to enable the future transparent side avatar slot
   - `--whisper-model base` to change the `faster-whisper` alignment model
   - `--no-whisper` to disable word alignment and use sentence-level subtitles
4. Review the generated `video-review.json`.
5. Then verify `build-summary.json` contains:
   - `tts_reference_id == female_student`
   - `html_baseline == light`
   - `style_review.status == pass`
   - `alignment_review.status == pass`
   - `media_alignment_review.status == pass`
6. Compare the generated stills with the light HTML baselines. If the gap is still obvious, iterate again before calling the build reviewable.
7. If the user wants publication packaging, run the multi-platform publisher skill on the same report and generated video path.

## Implementation Notes

- This skill is intentionally **local-first**:
  - orchestration is done in Python,
  - visuals are rendered in Remotion with React,
  - default output stays at `1920x1080 / 16:9 / 60fps`,
  - narration defaults to Fish Speech and falls back to macOS `say`,
  - audio is normalized locally with `ffmpeg`,
  - subtitle timing uses `faster-whisper` when available and script-derived word timing otherwise.
- The active house style is the `light` Lumi baseline, not the older dark/screenshot-heavy layouts.
- `display_title` may keep brand naming, but `spoken_title` and subtitles should prefer Chinese-friendly spoken aliases.
- **Content tone**: Lumi is a friendly morning news anchor, not an AI analyst. Scripts must:
  - be understandable to a non-CS college student — no jargon without explanation,
  - never use lecturing phrases like "先记住两点", "最关键的有两点", "说白了" — these sound like an AI summary, not a person talking,
  - transitions between items must be **content-based**, not mechanical numbering. Examples:
    - same company: "还是OpenAI，..." / same topic: "顺着这个话题，..."
    - product→testing: "说完产品，看看评测这边，..." / contrast: "评测之外，开源这边也有动静，..."
    - do NOT use "先说第一条" → "接下来" → "第三件事" patterns,
  - when mentioning a person or company for the first time, add a brief intro: "Karpathy，前特斯拉 AI 总监，..." / "Anthropic，Claude 背后的公司，...",
  - facts should flow as one sentence connected by "同时/而且/并且", NOT mechanical "第一...第二..." lists,
  - takeaway uses conversational prefixes: "简单来说", "这意味着", "换个角度看",
  - avoid English terms unless they are universally known (e.g., AI, App) — translate or explain everything else,
  - subtitles must NOT end with punctuation marks (no trailing 。，！ etc.), max 28 chars per line,
  - intro should sound like a person greeting you: "早，我是 Lumi" not "这里是 Lumi 的 AI 速递".
- **Human narration bar**:
  - Open from a human scene: repeated edits, waiting, approval, budget anxiety, or trust friction before naming the technical mechanism.
  - Avoid overusing abstract phrases such as "系统能力", "正式工作流", "能力边界", "入口", "基线"; translate them into who saves time, who can approve, who pays, or who takes the risk.
  - Outro slogan / issue quote must be a Chinese version of a real famous quote with an author, not a Lumi-invented aphorism.
- **Screen card rules**:
  - Top navigation item labels should be 4-8 Chinese characters and read like clickable mini-titles, not internal abbreviations.
  - Screen card bodies may use `；` to create 2-3 short visual bullet points.
  - Card icons should vary by story role: creative, compliance, research, tooling, cost, evaluation, risk, and workflow should not all reuse the same symbol.
- **Cover rules**:
  - Titles must be clickbait-friendly and understandable to general audiences: "AI行业又变天了" not "门槛换地方了".
  - Every cover must have exactly two lines of copy: `marketing_headline` (6-14 chars) + `subhead` (6-12 chars).
  - Every cover must include Lumi as a close 藤原千花 / Chika Fujiwara style restoration: pale pink hair, large black bow, warm playful expression, white school-uniform blouse, black shoulder straps/ribbon details, and a small readable `Lumi` chest badge. Lumi occupies ≤15% of canvas.
  - Cover generation uses the system imagegen skill first; deterministic local collage is only a layout-debug fallback.
- **BGM rules**:
  - Default BGM: `/Users/dystopia/.openclaw/workspace/assets/bgm-lofi-morning.mp3` (Lofi Morning Music).
  - BGM plays only during intro and outro, with 1.5s fade transitions. Silent during item narration.
  - Volume: 0.32 base, reduced to 55% when voice is active.
- **Image rules**:
  - Every item must have at least 2 relevant images. No blank/whiteboard slides allowed.
  - If primary source fetch fails, run broadened search fallback with relaxed scoring.
  - Hard-reject paper PDFs, arxiv screenshots, and text-heavy browser captures.
  - Internal metadata labels like "配图 2/2" must never appear in the final video.
- Do not route this through Sora or a paid API unless the user explicitly wants generative video instead of a reproducible news-card pipeline.
- If image fetching fails after all fallbacks, the build should still complete with fallback artwork cards (gradient + icon), never blank white.
- Intro GIF assets should be staged as short `mp4` loops before Remotion consumes them; do not rely on browser GIF timing in the final render.
- Reject generic webpage screenshots, docs previews, and off-topic meta images even if they technically score high.
- Only accept fallback search media when the search-result title, source domain, or image URL clearly matches the current story topic.
- Keep the default BGM audible under narration instead of burying it in the mix; verify in the rendered summary and final audio track.
- If remote TTS fails, continue with local narration and keep the build green.
- Keep the video outcome faithful to the report. Do not invent extra stories or stretch beyond the selected shortlist.
- If the report only has 3-5 strong items, keep that smaller set. Do not create filler cards just to reach 6.
- Treat the formal video-build directory as the source of truth for review and downstream delivery:
  - only call an artifact “latest reviewable” when the same `build/video/` directory contains both `build-summary.json` and `remotion-manifest.json`,
  - and the directory also contains the final `mp4`, `srt`, `slides/*`, and `video-review.json`,
  - do not treat an ad-hoc Remotion preview render as the final review build,
  - the 06:00 pipeline copies only the formal `video.mp4` and `video.srt` into `final/` for users and publish manifests,
  - `cover_image` / `video_cover_image` in `build-summary.json` are video still assets, not the daily social cover.

## Output Contract

Always return:

- Result: success/failure
- Video file: absolute path
- Summary JSON: absolute path
- SRT: absolute path
- Cover image: absolute path if available
- Video cover image: absolute path for `video_cover_image`
- Notes: anything that fell back, such as text-only cards, rejected media, local-voice fallback, or style/alignment warnings
