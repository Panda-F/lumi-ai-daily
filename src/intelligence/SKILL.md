---
name: ai-daily-intel
description: Generate a high-signal AI daily / 科技日报 focused on Silicon Valley product hotspots and research trends (24h hot window by default). Uses high-signal non-official technical X posts (builders/founders/PMs/researchers) plus primary-source verification; targets 6-8 body items total with up to 5 Silicon Valley tech hotspots and up to 3 research hotspots, prioritizing pull-worthy热点 and独家深度判断 over generic recap.
---

# AI Daily Intel

Use this skill when the user asks for `AI 日报`, `科技日报`, a merged `HackerNews-Deep-Dive + ArXiv-Daily-Digest`, or a high-signal AI/ML briefing with strong builder commentary.

This skill is the merged successor to the old `HackerNews-Deep-Dive` and `ArXiv-Daily-Digest` workflow.

## Read First

1. Read [`references/source-playbook.md`](references/source-playbook.md) for source lanes, scoring, and rejection rules.
2. Read [`references/high-signal-sources.md`](references/high-signal-sources.md) for the user-curated priority seed sources.
3. Read [`references/report-template.md`](references/report-template.md) for the required output structure (default target: 6-8 items, with up to 5 tech + up to 3 research, Telegram-optimized).
4. Read [`references/rsshub-discovery.toml`](references/rsshub-discovery.toml) before discovery runs that use the RSSHub cache.
5. Use `/Users/dystopia/.openclaw/workspace/scripts/tech_daily_feed_healthcheck.py` when you need to verify that the configured discovery feeds are actually reachable before a daily run.
5. If the run asks for a Telegram cover image, also read `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/SKILL.md` before finishing.
6. If the user wants a narrated video version, also read `/Users/dystopia/.openclaw/workspace/skills/tech-daily-video-factory/SKILL.md` after the Markdown report is written.
7. If the user wants Xiaohongshu / Zhihu / Telegram / YouTube / Bilibili publishing drafts, also read `/Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/SKILL.md` after the Markdown report is written.

## Core Workflow

1. Build a candidate pool from **two primary lanes** (tech + research):
   - **Silicon Valley tech lane (primary)**: brand-new AI products, feature launches, distribution/UX shifts, pricing/model packaging changes, enterprise adoption signals, major company moves that change product shape or developer workflow.
   - **Research lane (primary)**: fresh, high-impact papers and technical writeups (arXiv + reputable lab blogs + high-signal personal technical blogs) that could change products in 3–12 months.
   - Use X + 知乎 / 中文 roundup cross-check lanes mainly for **trend detection + sharp takes**, but also scan high-signal longform blogs from senior practitioners and researchers when they add original analysis or early framing.
   - Start from the user-curated seed list in `references/high-signal-sources.md` before broadening out.
   - Social-account scope must skew toward people who are close to the work: independent builders/researchers/operators with original judgment, senior engineering / research / product / management voices inside big tech, and frontier AI startup / unicorn accounts that are directly involved in shipping or research.
   - Discovery quota is mandatory before final selection: at least **20 candidates total** with **X >= 8**, **official/research/longform artifacts >= 8**, **知乎回答 / 专栏 / 中文 roundup >= 3**, and **RSS / community-discovered candidates >= 3**.
   - Within that pool, aim for at least **4 X candidates** from the curated seed list or one-hop similar accounts, and at least **3 longform candidates** from the curated blog/newsletter list or comparable authors.
   - Prefer a **discovery cache first** pass before manual widening:
     - if your exec environment dislikes compound shell commands, prefer the single helper entrypoint:
       - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_prepare_discovery.py --date YYYY-MM-DD`
       - it reuses an existing same-day `merged-candidates.json` when that cache is already populated, and only regenerates the missing discovery artifacts.
     - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_rsshub_discovery.py --config /Users/dystopia/.openclaw/workspace/skills/ai-daily-intel/references/rsshub-discovery.toml --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/rsshub-candidates.json`
     - Treat `merged-candidates.json` as the default seed pool, not as final evidence. It combines RSSHub/RSS with early-signal lanes for people voice, product-shadow monitors, and research velocity.
   - Then derive the day's manual search terms from that feed output instead of using fixed query clusters:
     - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_search_terms.py --discovery-json /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/merged-candidates.json --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/search-terms.json`
     - prioritize the generated `zhihu`, `zhihu_juya`, `blogs`, `official`, and `media` query variants.
2. Discovery & verification:
   - Default model policy:
     - use `gpt-5.4` for discovery, source triage, quote extraction, shortlist note-taking, final selection, conflict resolution, cross-item synthesis, and the final archive / Telegram write-up.
     - do not use mini models in the AI Daily workflow; if `gpt-5.4` is unavailable, fail loudly instead of silently degrading content quality.
   - Control token burn by narrowing the candidate pool before deep reading, not by downgrading the model.
   - Use a **coarse-to-deep** reading pass to control token burn:
     - first pass: skim titles, snippets, visible summaries, source metadata, and search-result context for the full candidate pool,
     - second pass: narrow to roughly **14-18** shortlist candidates,
     - deep read only when a candidate is likely to survive or when a key fact is still uncertain.
   - After discovery, run the local candidate review helper before final selection when possible:
     - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_candidate_review.py --discovery-json /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/rsshub-candidates.json --source-pack /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/source-pack --lookback-hours 24 --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/candidate-review.json`
   - Use the candidate review output to:
     - reject candidates marked `duplicate_within_hot_window`,
     - reject `same_day_trend_conflict` entries from the body shortlist,
     - prioritize items with `passes_depth_gate=true`, a non-empty `decision_impact`, and `selection_fit in {pullworthy_hotspot, deep_original, hot_and_deep}`,
     - actively demote `generic_low_signal=true` entries, reposts, and meta-discourse chatter.
   - Prefer **text-first verification** for primary sources: `web_search` / Tavily -> official URL -> `web_fetch`.
   - Use a single fallback chain for normal pages: **official URL -> `r.jina.ai` mirror -> `web_search` snippet -> drop**.
   - For arXiv specifically, use a stricter fallback: **`abs` page -> `web_search` abstract snippet -> drop**. Do not keep retrying mirrors for arXiv in this workspace.
   - Reserve `browser` mainly for the **cover image chain** and only use it for source verification when text-first methods fail.
   - Do **not** burn turns on repeated browser screenshots just to read article text. At most 1 browser open + 1 snapshot attempt for a verification page before falling back to another source.
   - If you open a verification page in `browser`, close that tab as soon as the needed text or screenshot is captured unless the same tab is still needed for the image chain.
3. X extraction is mandatory at the candidate stage:
   - build a shortlist of candidate X posts / threads before final selection,
   - prioritize accounts with original technical judgment over generic news or commentary accounts,
   - for every selected X-led item, try `x-reader` on the exact status URL,
   - if the selected item is not X-led, you may still use X as supporting context, but keep the primary link first-party.
4. Chinese-community cross-check is also mandatory at the candidate stage:
   - search indexed 知乎回答 / 专栏 (`zhihu.com`, `zhuanlan.zhihu.com`) from engineers, researchers, PMs, founders, investors, or operators who show first-hand judgment rather than hot-list commentary,
   - always include `橘鸦Juya` as a Zhihu cross-check lane for the day whenever a generated hot topic has a plausible China-facing angle,
   - always include `橘鸦AI早报 RSS` as a fixed roundup lane for detecting which topics have already entered the Chinese practitioner discussion cycle,
   - treat Zhihu / Chinese roundup sources mainly as discovery and framing input unless the post itself is first-hand evidence.
5. High-signal longform blogs are also in scope:
   - include personal technical blogs / research blogs from senior practitioners, lab leaders, staff+ engineers, and independent researchers when they provide first-hand conceptual framing or technical depth,
   - examples include `latent.space`, `jack-clark.net`, `simonwillison.net`, `interconnects.ai`, `gwern.net`, and `lilianweng.github.io`, but prioritize the author profile over any single domain,
   - use these blogs either as direct research/trend items when recent enough, or as supporting context that sharpens an emerging Silicon Valley AI trend.
6. For X verification:
   - Collect all candidate X URLs into a temporary file (one URL per line).
   - Run `python3 /Users/dystopia/.openclaw/workspace/skills/x-reader-skill/x-reader.py --batch <urls-file> --out <results.json>` to read them in a single safe browser session with built-in human-like delays and anti-ban guards.
   - Parse the results JSON: entries without `"error"` contain the full tweet text (including thread continuation) in the `"text"` field; use `"focal_text"` for the main tweet only.
   - If an entry has `"error"`, treat it as a failed read and fall back to a `web_search` result snippet for the exact status URL.
   - Do NOT call x-reader more than once per daily run (the batch mode handles multiple URLs in one session).
   - Do NOT open individual X pages in `browser` just to recover a short quote — use the x-reader batch output or a search snippet.
7. For 知乎 / 中文 roundup verification:
   - prefer `web_search` result snippets or plain-text mirrors when the page is indexed,
   - do not rely on inaccessible login walls as the only evidence,
   - shortlist candidates should go through Playwright-backed extraction via `/Users/dystopia/.openclaw/workspace/scripts/archive_social_sources.py`, which now marks blocked/generic pages as `partial`/`failed` and emits `usable_for_scoring`, `blocked_reason`, `duplicate_key`, plus downloaded `assets.json` / `images.json` metadata for images, video, audio, PDF, and other document links when available,
   - if a Zhihu / Chinese roundup claim cannot be tied to a first-party artifact or a clean quotation path, use it only as discovery context or drop it.
8. Use `summarize` only after the primary URL is selected (to speed up long reads).
9. Score candidates on novelty, product impact, technical depth, and verifiability.
   - Use this ranking order:
     1. **Verifiability**: unverifiable candidates should be dropped first.
     2. **Recency**: favor the current 24-hour hot window unless the user asks for a wider window.
     3. **Product impact**: workflow-shifting product or developer changes beat abstract commentary.
     4. **Technical depth**: concrete mechanism, metric, or implementation detail beats generic opinion.
     5. **Source independence**: author / operator / maintainer > direct reporter > aggregator.
   - Add a hard negative score for **obviousness**:
     - if a candidate feels like mainstream recap, executive PR, or “everyone already saw this headline,” it should lose to a narrower but sharper builder-facing signal.
   - Every shortlisted candidate must answer a **depth gate** before it can survive:
     - which class of practitioner does this affect,
     - which concrete product / engineering / research decision changes because of it.
   - If the candidate review JSON leaves `decision_impact` empty, do not force it into the final set.
   - Strongly favor emerging Silicon Valley AI patterns that are still forming: repeated concept words, workflow changes, eval / harness practices, agent behavior shifts, enterprise adoption patterns, packaging / pricing moves, or research ideas beginning to enter product conversations.
10. Cross-validate before final selection:
   - narrow the shortlist to the **best final set** only after comparing overlap and disagreement across multiple lanes,
   - prefer items that are supported by at least **2 independent evidence lanes** such as X + official source, 知乎 / 橘鸦RSS + official source, blog + repo/paper, or X + blog + official source,
   - if a genuinely new item has only a single direct first-party source, it may still be selected, but mark the item as `[单源]` rather than pretending it has a second lane,
   - if sources disagree, trust first-party artifacts and directly verifiable facts over commentary,
   - if two candidates are similar, keep the one with the stronger primary evidence and the sharper non-obvious takeaway.
   - enforce **selection diversity** before locking the final set:
     - do not let one company family occupy more than **2** body items unless the user explicitly asks for company-focused coverage,
     - prefer the final set to include multiple non-official high-signal lanes such as X / 知乎 / 中文 roundup / longform blogs whenever strong candidates exist,
     - prefer at least **1** RSS / community-discovered item that is later verified back to an official artifact or paper when a high-quality candidate exists,
     - at least **1** final item should carry meaningful 知乎 or 中文 roundup signal when a high-quality candidate exists; if none survives, note that explicitly in working notes rather than silently dropping the lane.
11. Keep only items anchored by a primary source (or a first-party technical thread).
12. Save the final archive report to `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md` unless the user asks for another path.
   - If this is a same-day manual rerun and a fresh archive Markdown already exists, you may reuse it only when it already matches the current capped structure; otherwise rebuild the report before delivery.
13. After the archive report is written, save a local social-source dossier for follow-up Q&A:
   - create `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.social-urls.txt`,
   - include every X / 知乎 / 中文 roundup URL that appears in the final report **or materially informed the final selection**, one URL per line,
   - always include the X URLs used by `硅谷风向词`,
   - then run:
     - `python3 /Users/dystopia/.openclaw/workspace/scripts/archive_social_sources.py --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md --urls-file /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.social-urls.txt --out-dir /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/source-pack`
   - the script writes a durable local source pack with per-source files plus `index.json`, `README.md`, `all_text.md`, and per-item `assets.json` / `images.json` manifests with downloaded assets when available,
   - if a source cannot be fully extracted, keep the raw HTML / JSON / mirror text when available and let the source pack mark it `partial` or `failed`; do not silently skip it.
14. Before the body items, add a short `硅谷风向词` opener:
   - summarize **2-3 concept-level terms** that are visibly circulating on X in the last **7 days** whenever possible, and never exceed **14 days**,
   - terms should be concept words or frames (for example `Harness`, `Computer Use`, `Orchestration`), not just product names,
   - each concept must be backed by at least 1 real X status URL that you can cite later if asked,
   - exclude words that have already been generic common sense for **30+ days**,
   - exclude words that appear on only 1-2 isolated accounts and have not actually formed a trend,
   - keep the write-up factual and compact; this section is for "what SV is currently repeating", not your own prediction.
15. If the run asks for a cover image:
   - fetch 3-6 real story images from the selected source pages,
   - when extracting cover assets from the report, prioritize original source pages over `x.com` / social discussion links; social links are evidence lanes, not preferred image lanes,
   - if a shortlisted paper is on `arXiv` and the abstract page only exposes a generic logo, allow the fetcher to use a PDF first-page preview as a supporting visual,
   - do not let chart screenshots, benchmark scorecards, browser UI captures, or QR pages consume the limited cover-asset slots unless the user explicitly wants them,
   - before assembling the cover, always generate `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.cover-copy.json` with:
     - `python3 /Users/dystopia/.openclaw/workspace/scripts/generate_tech_daily_cover_copy.py --report /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.md --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/tech-daily-YYYY-MM-DD.cover-copy.json`
   - that JSON must include one **daily marketing headline** plus the supporting subhead and side cover lines,
   - generate the title pack before the cover brief so WeChat, B站, video, and file name use one unified public title while cover copy uses a shorter visual hook from the same thesis,
   - prepare `cover-lab/imagegen-cover-brief.md` and `cover-lab/imagegen-cover-brief.json` with `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/prepare_imagegen_cover_brief.py`,
   - use the system imagegen skill as the default final cover path and save the selected 16:9 result to `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/cover-lab/final-cover.png`,
   - preserve Lumi's recognizable identity: pink long hair, black bow, friendly anime AI host; keep Lumi in a lower corner and no larger than 15% of the frame,
   - other than Lumi, the composition, typography, palette, cropping, and visual metaphor can change freely if the result is more clickable and truthful,
   - keep `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/scripts/assemble_magazine_cover.swift` only as the deterministic fallback or layout-debug path,
   - for the tech daily default cover style, read `/Users/dystopia/.openclaw/workspace/skills/plus-media-factory/references/tech-magazine-cover-style.md` and use the first short-video reference hierarchy as the style reference,
   - adapt that hierarchy to a 16:9 social cover: one dominant real-news visual, one huge readable hook, one short subhead, and one optional evidence card,
   - prefer a true article hero/OG image as the dominant background; use paper previews only as optional sticker/supporting material when necessary,
   - send the finished image before the Telegram short text,
   - if imagegen is unavailable, use the deterministic fallback only as an explicitly marked fallback and keep `final-cover.json` honest about the provider.
16. Produce two outputs:
   - **Archive Markdown**: concise but complete, saved to disk.
   - **Telegram delivery text**: much shorter than the archive version, optimized for one readable message.
17. If the run also includes the daily video:
   - treat `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/build/video/` as the formal source of truth for video build internals,
   - only treat a video as the latest reviewable artifact when `build/video/` contains `build-summary.json`, `video-script.json`, and `remotion-manifest.json`, and `final/video.mp4` exists,
   - pass that video into the Telegram / publish bundle flow so the daily Telegram thread includes the resolved daily cover image, the video as a Telegram video message, and then the Telegram summary text,
   - do not reuse `build/video/slides/cover.png` as the daily social cover; social cover must come from the plus-media cover pipeline.

## Selection Rules

- Hard cap: **最多 8 条** body items.
- Category cap: **最多 5 条** tech/product/company hotspots + **最多 3 条** research-direction signals.
- Default target: **6-8 条** body items.
- Default composition target: **至少 3 条可引流热点** + **至少 2 条独家深度/非显而易见判断**，其余位置再补最强信号。
- Do not treat the cap as a quota, but also do not stop at 4 条 just because the first few items已经够写。默认应继续补足到 **6 条以上**，除非工作笔记能明确说明当天确实不够。
- Thin-day fallback: **5-6 条强信号** is better than **8 条平庸信息**.
- At least **2** items must be driven by non-official high-signal technical X discussion (builders/founders/maintainers), and must include a verifiable quote.
- Prefer the final set to be materially shaped by multiple non-official signal lanes: X / 知乎 / 中文 roundup / high-signal longform blogs, not just official launch posts.
- Prefer at least **1** final item surfaced by RSS / community discovery and then verified back to an official source, repo, or paper when a strong candidate exists.
- Every run must search X + 知乎 / 橘鸦RSS, and must also scan the curated high-signal blog/newsletter lane when relevant to the cycle.
- Start with the user-curated seed sources before broadening to generic search results.
- At least **4** X candidate URLs should come from the curated seed list or one-hop similar accounts.
- At least **3** longform/blog/newsletter candidates should come from the curated list or similar high-signal authors.
- At least **1** shortlisted idea should come from 知乎或中文 roundup when a high-quality candidate exists.
- Use coarse-to-deep reading: skim the full pool first, then deep-read only the shortlist and unresolved facts.
- Same-day duplicate guardrail: a single X status URL should not occupy both `硅谷风向词` and the body shortlist unless the day is unusually thin and the working notes explicitly justify the override.
- 24-hour duplicate guardrail: if the candidate review helper marks a URL or `duplicate_key` as already used within the current hot window, treat it as rejected unless there is a genuinely new first-party update.
- Final items should be the most information-dense and cross-validated candidates, not simply the first items found.
- Prefer each final item to be supported by at least **2 independent evidence lanes** whenever possible, but allow direct first-party `[单源]` items when the signal is fresh and clearly sourced.
- Do not let OpenAI / Anthropic / Google style official launch posts crowd out everything else. Default cap: **max 2 items per company family** in the body.
- Do not let “大公司发布会后续包装稿”挤掉更锋利的 builder / researcher 信号。单纯大厂新闻如果没有新的机制、工作流、成本或组织层拐点，应直接降级或淘汰。
- Pull-worthy 热点优先看这几类：
  - 新产品 / 新模型 / 新价格 / 新入口 / 新分发动作，
  - 会引发转发讨论的工作流变化、组织层拐点、企业采用信号，
  - 能让普通读者马上感到“这跟我有什么关系”的使用门槛变化。
- 独家深度优先看这几类：
  - 研究/产品里别人没讲透的机制变化，
  - 对 benchmark、成本、采用、边界条件的反直觉解释，
  - builder / researcher / operator 会真的据此改变决策的判断。
- 明确拒绝把以下内容混进最终 6-8 条：
  - RT / 转述型社交帖，
  - 纯情绪评论、圈内八卦、meta discourse，
  - 订阅攻略、价格薅羊毛、泛问答、经验贴，
  - 没有产品/工作流/机制增量的泛媒体 recap。
- Every final item should pass this test:
  - if you remove the company name, is there still a non-obvious industry signal left?
  - if not, the item is probably too generic.
- The opener must include **2-3** real X-backed `硅谷风向词`.
- Every opener concept must map to at least one concrete X status URL from the recent cycle, so you can answer "出处" later.
- Every run must leave behind a local social source pack under `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/source-pack` so later Q&A can read saved X / 社交源 material without re-fetching.
- The formal text compile should also leave behind a non-social reference pack under `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/reference-pack` so official blogs, docs, GitHub pages, and papers keep their正文 / assets without re-fetching.
- Every browser tab created by the run must be closed before the task is considered complete. Reused pre-existing tabs may stay open, but temporary verification / generation tabs must not.
- Avoid pure infra/serving/tooling updates unless they directly unlock a new product capability or cost curve shift.
- Prefer individual builders over brand or corporate marketing accounts.
- Favor three social-source buckets:
  - independent builders / researchers / operators with original takes,
  - senior engineers / research leads / PMs / managers / directors / VPs at big tech companies,
  - frontier AI startup or unicorn accounts that are close to product shipping or model work.
- Do not use shallow hype, repost aggregators, or low-signal engagement bait.
- Reject generic media, clipping accounts, translated reposts, and "everyone already knows this" mainstream headlines unless there is a fresh technical, workflow, org, or product-shape turn.
- If a tweet is only commentary on someone else's launch, verify the launch from the original source before including it.
- If a claim is a rumor, require 2 independent trustworthy sources or mark it `【未证实】`.
- Use `[单源]` only for a single direct first-party source that is clear but not yet second-source confirmed.
- Never invent metrics, release dates, benchmark numbers, quotes, or model names.
- Keep quotes short and directly verifiable.
- Do not open with a one-line summary or "核心结论".
- Do open with a compact `硅谷风向词` section before the body items.
- Prioritize sources that are easy to verify in plain text:
  - official blogs / release notes / docs pages with text mirrors,
  - arXiv abstract pages,
  - GitHub release notes / README / model cards,
  - deep personal technical blogs / research blogs from high-signal authors,
  - indexed 知乎回答页 / 专栏页 or their search snippets.
- If an official page cannot be read cleanly after `web_fetch` + one mirror retry, do not keep looping on that page. Switch to another official artifact or drop the item.
- A requested cover-image run is **not complete** right after writing Markdown. Finish the image-send step first, or exhaust the allowed retries and append the prompt to the Markdown file.
- For research items, shallow commentary is not enough. If you cannot clearly explain:
  - what the method changes relative to prior work,
  - what evidence or benchmark result matters,
  - what the real limitation / boundary condition is,
  - and what product or workflow consequence could follow,
  then drop the paper and pick a better-understood research item.

## Output Specs

### Archive Markdown

- Target length: **<= 3400 Chinese characters**.
- Structure: compact `硅谷风向词` opener + item body.
- `硅谷风向词`: **2-3 terms**, each with one short explanation and one traceable X URL.
- Each item: **title + content + interpretation + 1 source link + 1 ultra-short quote**.
- Research items must keep the same compact structure, but `内容` should explicitly mention the method / result delta, and `解读` should explicitly mention the limit or likely landing path.
- Use `状态：[单源]` only when the item is a clean first-party single-source inclusion.
- Use `状态：【未证实】` only for disputed or rumor-like claims.
- Do not write long scene-setting paragraphs or repeated caveats.
- Write like a **senior analyst / product strategist**, not like a news editor:
  - cut generic setup,
  - cut obvious praise,
  - prefer “what changed / why now / who gets pressure / what to watch next”.
- If an item cannot support a sharp professional angle in one sentence, drop it.

### Telegram Delivery

- Target length: **<= 2000 Chinese characters**.
- Keep the same final selection as the archive version; do not add extra items.
- Start with a short `硅谷风向词：词1 / 词2 / 词3` line or equivalent 1-2 line opener.
- Each item should stay at **title + short content + short interpretation**.
- Do **not** include per-item links.
- Append only the single hottest primary link of the day as the last non-empty line so Telegram can render the preview.
- Keep the text dense and readable; avoid generic filler.

## Reporting Style

- Output must follow the Telegram-optimized template in `references/report-template.md`.
- **Delivery structure (Telegram):**
  1) First send **one generated collage cover image** for the day (if browser automation is available).
  2) Then send the **daily video** from `/Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/final/video.mp4` when the video build exists and `build/video/` also contains `build-summary.json` + `video-script.json` + `remotion-manifest.json`.
  3) Then send the **short Telegram text**, not the full archive Markdown.
- Treat delivery as an explicit checklist:
  - archive Markdown saved,
  - local source pack saved,
  - cover image sent successfully or intentionally skipped after 2 failed attempts,
  - daily video sent successfully or intentionally skipped because the formal video build is not ready,
  - any browser tabs opened by this run closed,
  - only then output the Telegram short text.
- Images must be reliable:
  - Preferred: a 16:9 imagegen cover created from the title-cover brief and fetched real source images.
  - Deterministic real-image collage is a fallback or debugging artifact, not the preferred production cover when imagegen is available.
  - Avoid generic "AI wallpaper" compositions with unrelated icons or hallucinated UI.
- If the browser tool is unavailable, fall back to the OpenClaw CLI:
  - browser automation: `openclaw browser --browser-profile openclaw ...`
  - media delivery: `openclaw message send --channel telegram --target <chat-id> --media <file>`
- When using the CLI fallback, keep track of every target id returned by `openclaw browser open ...` and close those tabs with `openclaw browser close <target-id>` before finishing.
- Verification heuristics:
  - Use `browser` for `gemini.google.com` media generation and asset upload.
  - Use `web_fetch` or `r.jina.ai/http://...` for official release notes, blogs, docs, arXiv, and GitHub whenever possible.
  - Avoid screenshot-based reading unless the page is truly only accessible in-browser and the content is already visible above the fold.
- Write in Chinese, preserve original-language source names and quotations.
- Separate sourced facts from your own inference.
- Optimize for signal density, not completeness.
- Avoid PR tone and avoid filling space with generic trend talk.
