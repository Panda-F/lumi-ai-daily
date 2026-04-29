# Source Playbook

Read this together with `high-signal-sources.md`, which contains the user-curated priority seed list.

## Candidate Lanes

1. Builder signal:
   - Non-official technical X posts by researchers, engineers, founders, and maintainers.
   - Look for implementation notes, failure analysis, training/inference observations, benchmark caveats, or release reactions with substance.
2. Zhihu / Chinese roundup signal:
   - Indexed 知乎回答 / 专栏 plus structured Chinese roundup feeds from company accounts, founders, researchers, serious operators, product leaders, investors, and high-signal industry writers.
   - Good for Chinese-language framing, first-hand implementation context, translated discussion, and product / distribution analysis.
3. High-signal longform blogs:
   - Personal technical blogs and research blogs from senior practitioners, lab leaders, staff+ engineers, and independent researchers.
   - Include curated newsletters and essay-driven blogs when they add original judgment earlier than mainstream coverage.
   - Good for original conceptual framing, system-design lessons, postmortems, eval methodology, and early pattern recognition.
4. Media cross-check:
   - Fast English and Chinese media feeds such as BBC Technology / Business and IT之家.
   - Use them to widen discovery and cross-check company, policy, infra, and org news, but prefer official artifacts whenever a first-party source exists.
5. Research:
   - New arXiv papers in `cs.AI`, `cs.CL`, `cs.CV`, `cs.LG`.
   - Prefer papers with unusually strong results, novel methods, or broad downstream implications.
6. Open source and infra:
   - GitHub releases, model framework updates, serving/training infra, benchmark tooling.
7. Community validation:
   - Hacker News threads, issue threads, or engineering discussions that reveal what serious practitioners are focusing on.

## Social Account Filter

- Prioritize authors who are close to the work:
  - independent developers, researchers, founders, or operators with original judgment,
  - senior engineers, research leads, PMs, managers, directors, or VPs inside major tech companies,
  - frontier AI startup / unicorn accounts that are directly involved in model, product, or platform work.
- Extend the same standard to blogs: prefer blogs written by people who are close to the work, not SEO content farms or generic newsletter wrappers.
- Favor people who add first-hand implementation detail, product reasoning, or organizational context.
- De-prioritize accounts that mostly summarize, translate, or amplify other people without adding new signal.

## Seeded Discovery

- Start with the curated priority sources in `high-signal-sources.md`.
- When RSSHub is available, seed the run with the local discovery cache first:
  - If the exec environment has shell-preflight limits or you already have a same-day cache, prefer:
    - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_prepare_discovery.py --date YYYY-MM-DD`
    - This reuses a populated same-day `merged-candidates.json` and only regenerates missing artifacts such as `search-terms.json`.
  - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_rsshub_discovery.py --config /Users/dystopia/.openclaw/workspace/skills/ai-daily-intel/references/rsshub-discovery.toml --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/rsshub-candidates.json`
- The default preflight also writes early-signal artifacts:
  - `discovery/early-signal-candidates.json`: HN/Reddit/blog people voice, product-shadow monitors, arXiv/HF/GitHub research velocity.
  - `discovery/merged-candidates.json`: RSSHub/RSS plus early-signal candidates, deduped and scored for search-term generation and candidate review.
  - `qa/early-signal-preflight.json`: public-lane health summary. Optional authenticated lanes are best-effort and should not block the report.
- Immediately turn that daily feed output into search terms:
  - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_search_terms.py --discovery-json /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/merged-candidates.json --out /Users/dystopia/Desktop/AI-Daily-Reports/YYYY-MM-DD/discovery/search-terms.json`
- Only widen after the seeded scan is done, and only to authors who look meaningfully similar in role, depth, and signal quality.
- The goal is not raw breadth; the goal is to find people with earlier judgment and sharper framing than generic news circulation.

## Zhihu / Chinese Roundup Filter

- 微信 discovery is currently disabled by user preference. Do not run WeChat search or quota checks unless the user explicitly asks to re-enable it.
- 知乎优先找长期输出、有实名或清晰职业背景、回答里带一手实验/案例/踩坑细节的答主或专栏作者，而不是热榜搬运和“新闻复述型”回答。
- `橘鸦Juya` 作为知乎交叉信号源默认加入检索：优先把当天 RSS 热词和 `橘鸦Juya` 组合起来搜，作为“这件事是否已经进入中文从业者日报视野”的额外证据。
- 额外固定交叉源：`https://imjuya.github.io/juya-ai-daily/rss.xml`
  - 这是 `橘鸦Juya` 的结构化日报 RSS，可直接进入 discovery feed。
  - 用它来判断“哪些主题已经被压缩进中文日报视野”，不要把它当成一手事实源。
- 如果账号无法判断作者背景，或者内容只有情绪判断没有一手细节，降权或丢弃。

## Minimum Mix

- Hard cap: 8 items total.
- Category cap: up to 5 Silicon Valley tech/product/company hotspots + up to 3 research papers, datasets, or lab reports.
- Default target: 6-8 items total.
- Default composition target: at least 3 pull-worthy hotspots and at least 2 deep/original items when the day supports it.
- Do not treat the cap as a quota. If the day is thin, publish fewer items rather than lowering the bar, but do not stop at 4 items unless the day is genuinely weak.
- At least 2 selected items should be first surfaced or materially sharpened by non-official technical X signals.
- Prefer the selected set to be materially surfaced, sharpened, or reframed by multiple non-official lanes overall: X, 知乎 / 中文 roundup, or high-signal blogs.
- Prefer at least 1 selected item surfaced by RSS / community discovery and then verified back to an official artifact, repo, or paper when a strong candidate exists.
- Default concentration guardrail: no single company family should occupy more than 2 body items unless the day is dominated by one clearly industry-defining event and the working notes explain why.
- Start from the user-curated seed list in `high-signal-sources.md` before expanding to broad search.
- Discovery quota before final selection:
  - X status URLs: **>= 8**
  - 知乎 answers / articles / 中文 roundup artifacts: **>= 3**
  - official / research / longform artifacts: **>= 6**
- Within that pool:
  - curated-seed or one-hop-similar X candidates: **>= 4**
  - curated or similar longform/blog/newsletter candidates: **>= 3**
- Every run should also seed manual widening from the community RSS hotlist:
  - `linux.do/latest.rss`
  - `linux.do/top.rss`
  - `old.reddit.com` AI subreddit RSS feeds

## Triage Protocol

- Run candidate review in two passes:
  - coarse pass: titles, snippets, visible summaries, metadata, and source identity only,
  - deep pass: full fetch, summarize, or detailed reading only for shortlist candidates and unresolved claims.
- If the local candidate review helper is available, run it after the coarse pass:
  - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_candidate_review.py --discovery-json ... --source-pack ... --lookback-hours 24 --out ...`
- If feed reliability is in doubt, run a quick health check first:
  - `python3 /Users/dystopia/.openclaw/workspace/scripts/tech_daily_feed_healthcheck.py --config /Users/dystopia/.openclaw/workspace/skills/ai-daily-intel/references/rsshub-discovery.toml --check-x-browser`
- Use that output to reject:
  - `duplicate_within_hot_window=true`,
  - `same_day_trend_conflict=true`,
  - `passes_depth_gate=false`.
- Aim to reduce the full pool to roughly **14-18** candidates before spending heavier tokens.
- Do not deep-read every candidate page by default.
- Escalate to deeper reading only when:
  - a candidate is likely to make the final set,
  - a key fact is uncertain or contested,
  - a quote or metric must be verified exactly.

## Ranking Order

- Rank candidates in this order:
  1. verifiability,
  2. recency,
  3. product impact,
  4. technical depth,
  5. source independence.
- If a candidate fails badly on a higher-ranked criterion, do not let a lower-ranked strength rescue it.

## What Counts As A Good X Item

- The author is close to the work: researcher, maintainer, founder, operator, or respected reviewer.
- Bonus when the author is a senior big-tech practitioner or a frontier-lab / unicorn operator with direct exposure to product or model decisions.
- The thread contains concrete detail: architecture, benchmark caveat, training trick, eval result, failure mode, cost/performance tradeoff, or deployment note.
- The post triggered meaningful discussion or is obviously important despite modest engagement.

## Hard Rejects

- Official product marketing threads unless they are the only first-party artifact and technically substantive.
- Official blog posts or launch pages that stay at the level of “we launched X” without a sharper non-official builder / operator / researcher angle.
- Generic "AGI soon", fundraising gossip, vague teaser posts, screenshot-only hype, or recycled AI news aggregators.
- Broad media summaries, translated repost accounts, clipping accounts, and low-context influencer takes.
- Thin personal blogs or newsletters that only paraphrase public launches without first-hand reasoning.
- Thin 知乎搬运号、营销答主，缺少作者身份、一手截图或具体观察。
- Posts without enough context to verify who said what and why it matters.
- "Everyone already knows this" launch news unless there is a fresh technical, workflow, org, or pricing angle surfaced by a high-signal operator.
- Any item whose primary URL cannot be opened.

## Verification Order

1. Primary artifact:
   - official blog, GitHub release, arXiv paper, first-party repo, or the original technical X thread.
2. Supporting confirmation:
   - browser search, follow-on discussion, or a second credible source for rumors and market-moving claims.
3. Extraction:
   - use `x-reader` or `summarize` only after the source is selected.

## Cross-Validation Rule

- Final selection is a ranking problem, not a first-come list.
- Before locking the final set, compare overlap and disagreement across lanes.
- Prefer items supported by at least **2 independent evidence lanes**:
  - X + official source,
  - 知乎 / 橘鸦RSS + official source,
  - high-signal blog + repo / paper / release note,
  - X + blog + official source.
- If a genuinely new item only has one direct first-party source, it may still be selected, but mark it `[单源]`.
- Reserve `【未证实】` for disputed or rumor-like claims, not for clean single-source launches or papers.
- If sources conflict, prefer first-party artifacts and directly verifiable facts over commentary.
- If two candidates cover the same story, keep the one with the stronger primary evidence and the sharper non-obvious takeaway.
- Do not let the same canonical X status URL appear in both `硅谷风向词` and the final item body unless the day is unusually thin and you explicitly note the override.
- If two or three official launches from the same vendor compete for slots, keep only the strongest one or two and use non-official lanes to look for the sharper market / builder / workflow signals elsewhere.
- If a candidate is still basically understandable as a generic PR headline after you remove the company name, it is too weak for the final list.
- If a candidate has only the official source and you cannot add a sharper second-order angle about mechanism, workflow, distribution, cost, or eval boundary, drop it.

## X Extraction Rules

- X extraction is required during candidate discovery, not optional polish at the end.
- Start with a shortlist of concrete X status URLs from builders/researchers/operators who are close to the work.
- Build a second shortlist from indexed 知乎回答 / 专栏 and `橘鸦AI早报 RSS`.
- Build a third shortlist from high-signal longform blogs when recent essays materially sharpen the trend.
- Seed all three shortlists from `high-signal-sources.md` first, then widen to adjacent same-profile sources.
- Build a second shortlist for `硅谷风向词`: 2-3 recurring concept words that multiple serious accounts are naturally repeating in the recent cycle.
- The social shortlists should skew toward original practitioners, senior big-tech voices, and frontier AI startup accounts instead of generic media or repost accounts.
- For each chosen concept word, keep at least one concrete X status URL so the report can answer follow-up source questions.
- For every X-led selected item, run `x-reader` on the exact status URL before quoting it.
- If `x-reader` fails closed, fall back to a search snippet for that exact status URL and keep the quote ultra-short.
- If an item has no usable X context and no strong first-party source, drop it.

## Trend Novelty Bias

- Optimize for emerging Silicon Valley AI trends, not consensus headlines.
- `硅谷风向词` time window:
  - prefer the last **7 days**,
  - never exceed **14 days**,
  - exclude terms that have already been common currency for **30+ days**,
  - exclude terms repeated by only 1-2 isolated accounts.
- Prefer:
  - new concept words showing repeated adoption across serious accounts,
  - workflow shifts that practitioners are suddenly converging on,
  - eval / harness / orchestration / agent-operation changes moving from niche to mainstream builder conversation,
  - new product-shape, pricing, packaging, or organization patterns inside frontier labs and big tech.
- De-prioritize:
  - launch recaps everyone has already seen,
  - obvious funding / keynote coverage with no fresh angle,
  - commodity "top 10 AI tools" style discourse.

## Research Deep-Read Standard

- A research item must answer four compact questions before it can survive:
  1. What bottleneck or task does it attack?
  2. What is actually new in the method or setup?
  3. What evidence suggests it matters?
  4. What limitation, assumption, or deployment boundary should the reader remember?
- If the paper cannot be explained beyond “性能更好 / 成本更低 / 很重要”, it is not ready for the final set.
- Prefer papers whose implications can be translated into product, agent, eval, data, or workflow consequences in the next 3-12 months.

## Fetch Strategy

- Prefer plain-text retrieval over visual browsing.
- Unified fallback chain for most pages:
  - official URL,
  - `https://r.jina.ai/http://...`,
  - `web_search` snippet,
  - drop the item.
- Default to coarse reading first; do not call heavier tools like full-page summarize unless the item survives the first pass.
- For 知乎 / 中文 roundup sources:
  - use `web_search` first,
  - prefer indexed canonical URLs or visible snippets,
  - shortlist candidates should then be passed through `/Users/dystopia/.openclaw/workspace/scripts/archive_social_sources.py`, which emits `usable_for_scoring`, `discovery_only`, `blocked_reason`, `duplicate_key`, extraction confidence, and `assets.json` / `images.json` metadata for each saved source,
  - if the full page is gated or unreadable, keep the claim short and verify the substance elsewhere.
- For personal / research blogs:
  - prefer canonical blog URLs first,
  - use text mirrors only when needed,
  - keep them as supporting context unless the essay itself is recent enough and directly advances the current trend cycle.
- After the final report is locked, archive non-social primary sources through `/Users/dystopia/.openclaw/workspace/scripts/archive_reference_sources.py` so the day folder keeps official/blog/paper正文 plus `assets.json` / `images.json` metadata locally.
- arXiv exception:
  - keep the `abs` / official article URL as the primary link,
  - use the search-result snippet as the short abstract/quote if fetch fails,
  - do not burn turns on repeated mirror retries for the same arXiv page.
- Use `browser` for verification only when text retrieval fails and the page is still worth keeping.
- Never spend multiple turns on repeated screenshots of the same page just to read article body text.
- If an item cannot be verified cleanly after one mirror retry and one in-browser snapshot attempt, drop it and move on.

## Thin-Day Policy

- Do not lower standards just to force the cap.
- If only 5-6 items clear the bar, publish 5-6 items and explicitly note that the day is thin.
- If fewer than 5 high-quality items exist, publish what is solid and say the signal day was unusually light instead of padding with noise.
- Six sharp items with real operator value are better than eight obvious items with brand-name gravity.

## Framing Checklist

- What actually happened today?
- Why should a builder, investor, or advanced user care?
- What is genuinely new versus recycled framing?
- What is the strongest verifiable quote?
- Which class of practitioner would be forced to change a concrete product, engineering, or research decision because of this?
