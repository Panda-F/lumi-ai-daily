# Title And Cover Playbook

This playbook is used when generating Lumi AI Daily's outward-facing title, Bilibili title, video title, WeChat title, and daily cover prompt.

## Priority

The title and cover are the day's traffic source. Treat them as product packaging, not decoration. They must be reviewed as hard as the facts.

## Core Principle

Title and cover must share the same traffic thesis, but they should not say the same sentence.

- The title carries the full promise: entity, action, proof surface, and consequence.
- The cover carries the instant hook: one big phrase, one visual conflict, one emotional or practical stake.

## Title Rules

Use concrete entities first:

- company, model, product, paper, tool, platform, team
- avoid abstract subjects like `AI`, `模型`, `新变化`, `重大突破` unless paired with a named entity

Use one of five formulas:

1. `Entity + action + consequence`
2. `Entity A vs Entity B + test surface + surprising result`
3. `Reader question + concrete proof`
4. `Old expectation -> new reality`
5. `Risk/loss frame + entity`

Good title traits:

- has a named entity in the first half
- includes a verb that actually happened
- tells the reader what changes for them: entrance, cost, workflow, risk, control, speed, trust
- creates a curiosity gap that the article/video can honestly close
- carries a human stake: waiting, repeated labor, creative agency, family safety, small-team access, trust, or loss of control

Avoid:

- pure code words without a scene
- fake crisis words
- "今日盘点", "六条新闻", "一文看懂"
- multiple same-day platform title variants that create review noise

## Unified Public Title

Use one outward-facing title for the day. Do not create separate WeChat, Bilibili, and video titles unless the user explicitly asks.

- The same title is written into `主传播标题`, `微信标题`, `视频标题`, and `B站标题`.
- The title should be human-readable first, then searchable: concrete entity, real action, and reader consequence in one sentence.
- The cover remains shorter and more visual; it should feel like a thumbnail hook, not a newsletter headline.

## Cover Rules

Main hook:

- target 4-12 Chinese visual characters
- hard max 18 characters
- use one strong word: `回归`, `开战`, `接管`, `翻车`, `真能用?`, `新入口`, `成本线`, `审计来了`

Subhead:

- target 6-16 Chinese visual characters
- explains the concrete consequence, not the same words as the main hook

Visual hierarchy:

- one dominant source visual
- one massive main hook
- one supporting subhead
- optional small evidence card
- Lumi character in a corner, visible but never larger than the story
- typography should feel hand-composed: aligned to the focal object, generous breathing room, thick readable strokes, no default AI poster lettering
- preferred cover type style: giant hand-brushed Chinese lettering on an irregular black brushstroke plate; one traffic keyword can be pink while the main characters stay warm white; use thick black inner contour plus clean white sticker-like outer stroke; keep dry-brush texture, slight kinetic tilt, and visible ink pressure so the thumbnail feels manually designed rather than AI typeset
- subhead treatment: put it on a separate black brush banner under the main hook, using pink/cream fill and bold readable strokes; it should clarify the human stake in plain language, not repeat the title

Reject:

- logos as the main image
- raw browser pages
- large unreadable charts
- multiple equal-weight screenshots
- more than two text zones
- fake claims not present in the report
- smooth generic sans-serif cover type, glossy bevel effects, chrome 3D letters, pseudo-Chinese glyphs, warped text, or dense neon strokes

## Psychological Hooks

- Information gap: show a specific unanswered question.
- Loss aversion: show what could be lost, broken, made costly, or made risky.
- Processing fluency: make the thumbnail parse in one second.
- Distinctiveness: one abnormal object, phrase, or comparison beats a collage.
- Authority: official product visuals, source screenshots, and named tests reduce clickbait risk.
- Human consequence: the hook should touch a person or role, not just a system. `设计师少返工` is stronger than `工作流升级`.

## Benchmarks From Current Creator Research

- Bilibili example: 影视飓风's `AI真的好用吗？影视飓风全新工作流分享！` works because it frames AI through a creator team's lived workflow, not through a model name. The title starts with a plain question, then promises an internal working method.
- YouTube thumbnail practice from MrBeast's team reinforces mobile-first reading and many title/thumbnail concept tests. For Lumi, use the principle without copying the loud style: one promise, one visible tension, and text that survives small-screen scanning.
- Do not repeat the full title on the cover. The cover should add a second, shorter emotional hook or scene cue.

## Output Contract

For title generation, produce:

- 主传播标题
- 正文标题
- 微信标题, same as 主传播标题
- 视频标题, same as 主传播标题
- B站标题, same as 主传播标题
- 封面主标题
- 封面副标题
- 文件名短标题
- 标题主语
- 标题动作
- 标题后果
- 封面左侧
- 封面右侧

For cover generation, prepare an imagegen prompt that includes:

- exact main hook text
- exact subhead text
- Lumi reference requirement
- selected source visual roles
- layout and negative constraints
