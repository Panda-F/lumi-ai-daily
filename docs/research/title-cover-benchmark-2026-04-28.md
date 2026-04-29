# Title And Cover Benchmark

Research date: 2026-04-28

This benchmark looks at Bilibili and YouTube creators in AI, tech, and knowledge communication. The goal is not to copy their style, but to extract packaging patterns that can improve Lumi AI Daily's daily title and cover.

## Bilibili Examples

| Source | Title | Visible Cover Hook | Observed Pattern |
| --- | --- | --- | --- |
| [Lau博士的云组会, DeepSeek V4](https://www.bilibili.com/video/BV1FWoGByEyU/) | 真王回归！！！DeepSeek系列最全回顾！无缝衔接V4！ | `DeepSeek V4` + `真王回归!` | Title sells completeness and continuity; cover compresses to a coronation hook. Human face plus large outlined text creates instant recognition. |
| [神烦老狗, DeepSeek V4 Pro vs GPT-5.5](https://www.bilibili.com/video/BV1tyoJBVEFV/) | DeepSeek V4 Pro大战 GPT-5.5：前端、写作、代码全测了一遍，结果很抽象！ | `DeepSeek v4Pro` vs `GPT5.5` + `裁判` | A/B conflict is visible before reading. The title promises a concrete test set and an unexpected result. |
| [影视飓风, AI工作流](https://www.bilibili.com/video/BV16woRBfEsH/) | AI真的好用吗？影视飓风全新工作流分享！ | `更新 工作流?` | Title starts from a broad audience question; cover uses one huge concrete outcome. Real UI background and creator face signal credibility. |

Local thumbnail evidence is stored under `docs/research/thumbnails/bilibili/`.

## YouTube Examples

| Source | Title | Visible Cover Hook | Observed Pattern |
| --- | --- | --- | --- |
| [Two Minute Papers](https://www.youtube.com/watch?v=Xf_v62TQOx4) | NVIDIA's New AI Broke My Brain | `NVIDIA AI IMPOSSIBLE!` | The title frames a credible expert's surprise; cover uses one impossible claim on a clean prop. |
| [Two Minute Papers](https://www.youtube.com/watch?v=Sk9tvyRSCgY) | DeepMind's New AI: A Gift To Humanity | Short high-stakes phrase | Strong entity plus civilizational consequence. |
| [Fireship](https://www.youtube.com/watch?v=jeA-KBv0b68) | Claude just got another superpower... | `CLAUDE DESIGN` | Meme metaphor plus sparse words. The title leaves the superpower unstated, creating a gap. |
| [Fireship](https://www.youtube.com/watch?v=-01ZCTt-CJw) | Google just casually disrupted the open-source AI narrative... | Sparse meme/brand composition | Irony and understatement make a technical shift feel social and consequential. |
| [Andrej Karpathy](https://www.youtube.com/watch?v=7xTGNNLPyMI) | Deep Dive into LLMs like ChatGPT | `ChatGPT` + visual stack | For high-trust deep dives, clarity and authority beat hype. The cover shows the object being explained. |
| [Matthew Berman](https://www.youtube.com/watch?v=tNV9_I-zLO0) | OpenAI just dropped GPT-5.5... (WOAH) | official-looking release screenshot + face | Breaking-news packaging: entity, drop moment, reaction. |

Local thumbnail evidence is stored under `docs/research/thumbnails/youtube/`.

## What Top Packaging Has In Common

1. The title and cover do different jobs.
   - Title: full promise, entity, test/result, reason to watch.
   - Cover: one visual question or one emotional verb.

2. The cover uses fewer words than the title.
   - Bilibili examples often use 4-10 large visual characters for the true hook.
   - The rest is carried by faces, product logos, UI, model names, and contrast.

3. There is usually a visible conflict.
   - Entity vs entity: DeepSeek vs GPT.
   - Old workflow vs new workflow.
   - Expected failure vs surprising success.
   - Official claim vs tested result.

4. A person or character anchors the frame.
   - Faces add intent, emotion, and scale.
   - For Lumi, the character should stay as a small recurring host/brand asset, not dominate the news image.

5. The strongest covers are legible at mobile size.
   - One focal subject.
   - One massive phrase.
   - High contrast.
   - No dense charts as the main background.

## Communication Psychology

- Information gap: curiosity rises when the audience can see a specific gap between what they know and what they want to know. Use a concrete missing answer, not vague mystery. Source: George Loewenstein's information-gap theory, summarized in [Information Gap Theory](https://www.ignorancegraph.com/information-gaps/information-gap-theory/).
- Loss aversion: people react strongly when a change may remove an advantage, break a workflow, raise cost, or create risk. Source: [Prospect theory](https://www.britannica.com/topic/prospect-theory).
- Processing fluency: people click what they can parse quickly. The cover must win the first second before the title does nuance.
- Von Restorff effect: one distinct visual object or phrase is remembered better than a cluttered set. Use one abnormal object, one face, or one highlighted word.
- Social proof and authority: credible entities, test conditions, official releases, and recognizable tools reduce the feeling of clickbait.

## Lumi Method

### Title Formula

Use one of these structures:

1. `Entity + action + consequence`
   - Example shape: `OpenAI把聊天框推成工作台`

2. `Entity A vs Entity B + test surface + surprising result`
   - Example shape: `DeepSeek和GPT正面跑工作流`

3. `Reader question + concrete proof`
   - Example shape: `AI真能改工作流吗？影视团队先交卷`

4. `Old expectation -> new reality`
   - Example shape: `浏览器不只是入口，AI开始接管长任务`

5. `Risk/loss frame + entity`
   - Example shape: `企业AI上线，审计风险先到`

### Cover Formula

The cover must be simpler than the title:

- Main hook: 4-12 Chinese visual characters when possible, max 18.
- Subhead: 6-16 Chinese visual characters.
- One dominant source visual.
- One clear emotional or consequence word: `回归`, `开战`, `接管`, `翻车`, `真能用?`, `成本线`, `新入口`, `审计来了`.
- Lumi remains visible as a small recurring host in a corner.

### Daily Decision Rule

Before generating title and cover, pick the day's traffic source:

- Breaking news: emphasize freshness and entity.
- Comparison/test: emphasize A vs B and result.
- Workflow/usefulness: emphasize before/after and concrete scene.
- Research/paper: emphasize impossible result, benchmark shock, or real-world consequence.
- Risk/policy: emphasize loss, compliance, or control.

If no traffic source can be named, the selected top story is probably wrong.
