---
name: plus-media-factory
description: Use when the user wants to generate images or videos with their own Gemini / ChatGPT / Sora web subscriptions via browser automation instead of paid APIs; includes Gemini reference-image collage workflows, asset harvesting from source pages, and reliable download delivery.
---

# Plus Media Factory (Browser automation)

Operate the user’s already-signed-in web sessions to generate media without calling paid model APIs.

## Preconditions (must confirm before running)

- User explicitly wants **web automation** (not API calls).
- A **persistent browser profile** is available and contains an active login:
  - Gemini: https://gemini.google.com
  - ChatGPT: https://chatgpt.com
  - Sora: https://sora.com
- Downloads directory is known (default: `~/Downloads/`).

If any precondition is not met, stop and ask for the missing detail.

## OpenClaw CLI Fallback

If the first-class `message` tool is unavailable in the current agent session, do **not** give up. Use the OpenClaw CLI through `exec` instead:

- Message delivery:
  - `openclaw message send --channel telegram --target <chat-id> --media <file> --message "<caption>"`

For AI Daily / tech daily covers, default generation now runs through the system imagegen skill handoff brief described below. The Playwright helpers are legacy browser fallback/debug paths, with ChatGPT Images first and Gemini as fallback:

- `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/cover_browser_router.py`
- `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/chatgpt_cover_browser.py`
- `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/gemini_cover_browser.py`

If that managed profile is already open, the helper can attach to the existing OpenClaw Chrome instance over CDP instead of fighting the profile lock.

Keep `openclaw browser --browser-profile openclaw ...` only as a **diagnostic tool** for checking whether Gemini is logged in or inspecting the page manually. Do not use snapshot/ref clicking as the primary Gemini generation path anymore.

## Browser Cleanup Contract

- If you open any page or tab during the run, you own its cleanup.
- Prefer reusing one working tab per site instead of opening many parallel tabs.
- Close temporary source, asset, preview, or retry tabs as soon as they are no longer needed.
- Before the run ends, close every tab that was newly opened by this run.
- Do not close tabs that already existed before the run unless the user explicitly asked you to.
- For CLI fallback, keep the target id returned by `openclaw browser open ...` and close it with `openclaw browser close <target-id>` after the work is done.

## Safety / policy guardrails

- Don’t bypass paywalls, captchas, or account protections.
- Don’t attempt “session hijacking” against other people. Only use the user’s own local browser profile.
- If the site asks for re-auth / 2FA, ask the user to complete it manually.
- Only upload images the user has the right to use. Prefer first-party press / product / documentation images, public screenshots the user is authorized to reference, or user-owned assets. If rights are unclear, skip that asset.

## Step 1 — Classify the request

- If user asks for an **AI Daily / tech daily cover** → prepare the imagegen handoff brief first; use ChatGPT/Gemini browser fallback only if imagegen is unavailable or explicitly requested.
- If user asks for a general **image collage**, **cover**, **reference-guided generation**, or wants to combine real source images through their browser subscriptions → ChatGPT Images flow first, then Gemini fallback.
- If user asks for a simple **image** and explicitly wants ChatGPT → DALL·E flow.
- If user asks for **video** → Sora flow.
- If ambiguous, ask: output type (image/video), aspect ratio, duration, style references, and whether they want text in the image.
- For a tech daily / 科技日报 cover, also read `references/tech-magazine-cover-style.md` and treat it as the default layout style guide.

## Step 2 — Gather reference assets first

If the request is based on news items, reports, or named story links, fetch 3-6 reference images before opening the generation site.

- Prefer:
  - official OG / hero images,
  - product screenshots,
  - paper figures,
  - chart screenshots or first-party visual assets.
- Avoid:
  - tiny logos,
  - headshots unless the user explicitly wants them,
  - watermark-heavy editorial photos,
  - assets with unclear usage rights.
- Use the helper script when you have a report Markdown or a list of source URLs:
  - asset fetch:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/fetch_story_images.py \
  --report /abs/path/to/report.md \
  --out-dir /tmp/openclaw/story-assets/YYYY-MM-DD
```

- Review the generated `manifest.json` and keep only the strongest 3-6 assets.
- Treat social/X links as signal sources, not primary cover-image sources. The fetcher should prioritize original article pages first and let social links trail behind them.
- When the source is `arXiv`, allow the fetcher to fall back to a PDF first-page preview if the page only exposes generic logos.
- For tech daily covers, prefer 1-2 hero/OG/article visuals plus at most 1 document-like supporting visual; do not let benchmark charts, scorecards, tables, or browser screenshots dominate the final asset pool.
- If the manifest is dominated by charts, browser pages, or logos, trim it or rerun with explicit original-source URLs before assembling the cover.
- For tech daily / 科技日报 covers, generate the daily cover-copy JSON before assembling the fallback cover:

```bash
python3 /Users/dystopia/.openclaw/workspace/scripts/generate_tech_daily_cover_copy.py \
  --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md \
  --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.cover-copy.json
```

- This JSON should always contain one **daily marketing headline** plus the supporting subhead and side-cover lines.
- For AI Daily / tech daily cover requests, the default final-cover path is the system imagegen skill. Fetch real source visuals first, generate the title/cover copy JSON, then prepare an imagegen handoff brief:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/prepare_imagegen_cover_brief.py \
  --date YYYY-MM-DD \
  --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/final/report.md \
  --cover-copy /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.cover-copy.json \
  --title-pack /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/publish/title-pack.json \
  --story-manifest /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/assets/story/manifest.json \
  --final-cover /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/final-cover.png \
  --out-json /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/imagegen-cover-brief.json \
  --out-md /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/imagegen-cover-brief.md
```

- Use the generated `imagegen-cover-brief.md` with the system imagegen skill. Save the selected 16:9 result to `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/final-cover.png`.
- Preserve the Lumi host identity as a close 藤原千花 / Chika Fujiwara style restoration: pale pink hair, large black bow, warm playful expression, white school-uniform blouse, black shoulder straps/ribbon details, and a small readable `Lumi` chest badge. Keep Lumi in a lower corner and no larger than 15% of the frame.
- The image prompt may explicitly name 藤原千花 / Chika Fujiwara when generating Lumi covers.
- Other than Lumi, the composition, palette, typography, crop, and visual metaphor can change freely if the result is more clickable and truthful.
- For tech daily / 科技日报 covers, keep the magazine-cover compositor only as a deterministic fallback or layout-debug tool:

```bash
swift /Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/assemble_magazine_cover.swift \
  --manifest /tmp/openclaw/story-assets/YYYY-MM-DD/manifest.json \
  --out /tmp/openclaw/downloads/tech-magazine-cover-YYYY-MM-DD.png \
  --copy-json /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.cover-copy.json
```

- Use the magazine compositor as the deterministic fallback for tech daily covers because it preserves real assets while matching the short-video reference hierarchy more closely than a simple grid.
- The imagegen result is the baseline deliverable. The deterministic collage is not the production target when imagegen succeeds.
- The resolved final cover from this chain is the daily social cover that downstream Telegram / Bilibili / WeChat / X / YouTube manifests should reuse.
- If the user chooses a final cover through flexible GUI work, save that selected image to `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/final-cover.png` (or `.jpg/.jpeg/.webp`) so downstream publishing always reuses the same asset.
- Optional metadata can be stored beside it as `final-cover.json`; this is a lightweight handoff contract and is preferred over forcing every cover run into one rigid script.
- If `final-cover.json` records `ok=false`, `login_required`, `gemini_failed`, or another failed terminal stage, treat the handoff as failed and do not let downstream publishing assume `final-cover.*` is a valid final cover.
- Before any manual browser upload, stage the chosen reference images into `/tmp/openclaw/uploads/YYYY-MM-DD/` and upload only those staged copies.
- Browser-based ChatGPT/Gemini helpers are legacy fallback/debug paths, not the default AI Daily cover path.
- For legacy browser fallback, use `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/cover_browser_router.py`. It writes a structured final result JSON that downstream publishing can trust.
- The ChatGPT-first helper is `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/chatgpt_cover_browser.py`.
- Gemini remains the second-stage fallback helper at `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/gemini_cover_browser.py`.
- If you need to warm up the reusable login state for daily cover runs, first launch the dedicated OpenClaw browser profile with:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/cover_browser_bootstrap.py
```

- This opens `chatgpt.com/images` and `gemini.google.com/app` inside the persistent `openclaw` browser profile at `/Users/dystopia/.openclaw/browser/openclaw/user-data`, so once the user logs in there, later daily runs can reuse the same session.

## Step 3 — Prompt shaping (lightweight)

Before typing into the site, rewrite the user prompt into a production prompt:

- Include: subject, environment, composition, camera/shot, lighting, style, constraints.
- If reference assets exist, assign each asset a visual role (hero panel, supporting module, chart tile, texture, interface card).
- Ask the model to **unify and editorialize** the references instead of copying them literally.
- Add a short **negative** list (avoid artifacts, extra limbs, watermarks, unreadable text).
- For video: add motion, pacing, lens language, and continuity constraints.
- For tech daily covers:
  - read `references/tech-magazine-cover-style.md` first,
  - use the first short-video reference image only as a **layout reference**,
  - keep one real full-bleed background, one top-left news card, one huge yellow-black marketing headline, one white supporting subhead, and one optional right-bottom sticker slot,
  - the largest readable element must be the daily `marketing_headline`,
  - treat social screenshots, QR pages, charts, scorecards, and reference images as non-background assets,
  - allow bright paper previews only as optional sticker/supporting assets when they are the only truthful secondary visuals,
  - filter out screenshots, QR pages, charts, and reference images before selecting the dominant background asset.

Keep the final prompt under ~1200 chars unless user asks for maximal detail.

## Step 4A — Legacy ChatGPT Images browser cover flow

1. Use `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/cover_browser_router.py` only for legacy browser fallback/debug cover runs.
2. That router should:
   - upload the local collage plus the strongest 2-4 references to ChatGPT Images first,
   - request one high-quality 16:9 cover that preserves the recognizable real-news visuals,
   - fetch the generated image through the logged-in browser context,
   - only call Gemini if ChatGPT fails or clearly cannot complete the run.
3. When a cover succeeds through ChatGPT, treat that result as the final cover handoff and do not continue to Gemini.
4. The ChatGPT result JSON should be considered successful only when `ok=true` and `downloaded` / `image` point to a real local file.

## Step 4B — Gemini image-composition fallback flow

1. Use the Playwright helper instead of ad-hoc browser clicks. Default behavior:
   - launch Chrome directly with `/Users/dystopia/.openclaw/browser/openclaw/user-data`,
   - if that profile is already locked by the managed OpenClaw Chrome, attach over CDP to `http://127.0.0.1:18800`,
   - open a fresh Gemini tab,
   - verify login state,
   - normalize to a new chat,
   - switch to `制作图片 / Create images`,
   - upload the staged collage plus 2-4 strongest references,
   - submit the prompt,
   - wait for the downloadable image,
   - save the result under `/tmp/openclaw/downloads`.
2. Default target for high-end cover work: **Gemini Pro**. If the quality picker is visible, switch away from `快速/Fast` for the cover run.
3. In the composer, send a message in Chinese:
   - “请基于我上传的本地拼贴底稿和参考图，输出 1 张 16:9 的新闻封面优化版。务必保留真实图片主体的可辨认度，只做排版、光影、质感和统一性优化，不要凭空替换成无关图像：<FINAL_PROMPT>”
   - If the image is for Telegram/news delivery, explicitly say:
     - clean short-video news layout,
     - preserve recognizable real news images,
     - no random extra text,
     - no logo wall,
     - no photobash seams,
     - no hallucinated unrelated icons or brains.
   - For tech daily covers, explicitly add:
     - short-video news cover hierarchy based on the first reference image,
     - one dominant real-news background image,
     - a huge yellow headline with heavy black outline,
     - a bold white supporting subhead underneath,
     - a top-left news card and an optional right-bottom sticker slot,
     - darkened background with clean separation between headline and imagery,
     - keep the final cover truthful to the report and do not invent fake clickbait claims.
4. Retry policy:
   - on a generic Gemini failure or obviously poor composition, do **one** full fresh-tab retry,
   - simplify the prompt and reduce asset count on that retry,
   - if both attempts fail, return the local collage as `provider=fallback_collage`,
   - if Gemini clearly requires login / 2FA, return a structured `login_required` failure instead of pretending the site is unstable.
5. The helper must always emit a structured JSON result containing:
   - `ok`
   - `provider` (`gemini` or `fallback_collage`)
   - `attempts`
   - `final_stage`
   - `downloaded`
   - `artifacts`
   - `fallback_reason`
6. Use the helper’s result JSON as the source of truth for success/failure. Do not infer outcome from stray stderr text.

## Step 4C — Direct DALL·E / ChatGPT image flow

1. Open `https://chatgpt.com` in the browser.
2. Ensure you are in a chat where image generation is available.
3. In the composer, send a message in Chinese:
   - “请用 DALL·E 生成：<FINAL_PROMPT>”
   - If user needs multiple variations: explicitly ask for N variants.
4. If ChatGPT returns a generic failure such as “Something went wrong”, retry once in a fresh chat or an existing successful DALL·E thread before giving up.
5. Wait for image(s) to render.
6. Deliverables:
   - Prefer downloading the original image(s) to `~/Downloads/`.
   - If download UI is unavailable, extract the rendered image URL(s) and download.
7. Return to the user:
   - File path(s)
   - The exact prompt used

Use this direct flow only when:

- the user explicitly asks for ChatGPT / DALL·E only, or
- you are debugging ChatGPT generation itself rather than the default ChatGPT→Gemini router.

## Step 4D — Sora video flow

1. Open `https://sora.com`.
2. Create a new generation.
3. Set defaults unless user overrides:
   - Duration: **5s**
   - Resolution: **480p** (cheapest)
   - Aspect: keep default unless specified
4. Paste the optimized prompt.
5. Click **Generate**.
6. Monitor progress:
   - Poll every 20–30s.
   - Timeout guidance: after ~8 minutes with no progress, stop and report.
7. When finished, download `.mp4` to `~/Downloads/`.
8. Return to the user:
   - File path
   - Settings used (duration/resolution/aspect)
   - The exact prompt used

## Step 5 — Output contract

Always reply with:

- **Result**: success/failure
- **Files**: absolute local path(s)
- **Prompt used**: final prompt text
- **Asset manifest**: absolute path, if reference assets were used
- **Local collage**: absolute path, if a deterministic real-image collage was built
- **Result JSON**: absolute path, when the Gemini helper was used
- **Settings** (video only)

If the user wants the file sent to a chat channel (Telegram/WhatsApp), ask which channel/recipient and confirm before sending.
Exception: if the current run already provides an explicit delivery target (for example a cron task bound to a known Telegram chat), use that target directly instead of asking again.

## Step 6 — Cleanup

- Close every browser tab created by this run before returning control.
- If you reused an existing Gemini / ChatGPT / Sora tab, leave that reused tab in place but close any helper tabs opened by this run.
- If cleanup fails, report which page is still open and why.
