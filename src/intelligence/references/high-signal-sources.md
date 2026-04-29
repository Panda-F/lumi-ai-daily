# High-Signal Sources

Use this file as the default discovery seed list for the tech daily workflow.

These are user-curated sources that tend to surface original judgment, technical framing, or early signals before mass-market coverage catches up.

## Working Rules

- Start every tech-daily run from this seed list before widening out to broader search.
- Treat this as a priority seed list, not a closed allowlist. Expand one hop to adjacent accounts or blogs only when they fit the same profile.
- Do not force a seed source into the final report if its current-cycle content is only reposting obvious news.
- Prefer original posts, original essays, original podcasts/newsletters, and first-hand technical notes over summaries.
- When one person publishes on both X and a blog/newsletter, scan both lanes.

## X Priority Seeds

### First-Line Engineers / Researchers

- `@karpathy` (Andrej Karpathy): first-line coding-agent, harness, and computer-use framing. Treat as a core account and do not auto-remove it on one flaky profile probe.
- `@hardmaru`: research-to-product bridge thinking, agentic research workflow signal, and unusually original technical framing.
- `@fchollet` (Francois Chollet): independent criticism of LLM capability limits and evaluation.
- `@swyx` (Shawn Wang): early trend naming and AI engineering framing; also cross-check with `latent.space`.
- `@simonw` (Simon Willison): practical LLM engineering, daily experiments, and low-noise findings.
- `@natolambert` (Nathan Lambert): RLHF, post-training, and model-training detail; also cross-check with `interconnects.ai`.
- `@rasbt` (Sebastian Raschka): unusually strong longform technical breakdowns on LLM architecture, training, and systems tradeoffs.
- `@_philschmid` (Philipp Schmid): close-to-the-work open-model deployment, inference, and model-integration signal.
- `@CGoldie` (Chris Olah): interpretability and deep conceptual work; sparse but high-value.

### Independent Researchers / Sharp Thinkers

- `@emollick` (Ethan Mollick): first-hand experiments about AI in work and education.
- `@jerryjliu0` (Jerry Liu): agent/RAG/document workflow signal from someone shipping in the stack.
- `@eugeneyan` (Eugene Yan): applied ML judgment, evaluation framing, and production-facing AI systems thinking.
- `@ClementDelangue` (Clement Delangue): open-model platform, data/storage abstraction, and ecosystem-shape signal from the Hugging Face side of the market.
- `@repligate`: agent behavior, emerging workflows, and early concept diffusion.

### Chinese-Language X Signals

- `@op7418` (Gui Cang / 歸藏): fast product and multimodal discovery.
- `@dotey` (宝玉): AI 产品体验、前沿模型实测、翻译引介硅谷动态，有自己的判断。
- `@FinanceYF5` (小互): AI 产业链和商业化视角，关注落地和资本。
- `@tuturetom` (花生酱Tom): AI 工程实践、Agent 开发、开源工具链。

## Chinese Domestic Sources (国内高信号源)

### 微信公众号 Priority Seeds

- `机器之心` (Synced): 最全面的中文 AI 技术媒体，首发翻译+原创分析。
- `量子位` (QbitAI): 产品发布、模型评测、行业动态，速度快。
- `新智元` (AI Era): 前沿论文解读、大厂动态、行业趋势。
- `36氪`: 商业化视角的 AI 报道，关注融资和产品落地。
- `极客公园` (GeekPark): 产品思维的 AI 报道，创始人访谈。
- `硅星人` (Guixingren): 硅谷+中国双视角，有独立判断。
- `AI工程化` / `AI寒武纪`: 偏工程实践的公众号，适合补充技术深度。

搜索方式：`web_search` 搜 `site:mp.weixin.qq.com "关键词" 最近24小时`，或直接搜公众号名+话题。

### 国内社区 / 论坛

- `即刻 (Jike)`: AI 话题圈子活跃度高，有很多一线从业者的碎片化洞察。搜索：`web_search "site:m.okjike.com AI"` 或 `"即刻 AI" + 关键词`。
- `少数派 (sspai.com)`: 高质量 AI 工具实测和工作流分享。
- `V2EX`: 开发者社区，AI 工具使用反馈和技术讨论。

### 国内高信号博客 / Newsletter

- `Founder Park` (极客公园旗下): 创始人视角的 AI 深度内容。
- `晚点LatePost` (latepost.com): 深度调查报道，大厂 AI 战略内幕。

## Zhihu Search Seeds

Primary author seed:

- `橘鸦Juya`: daily AI roundup / cross-check lane. Treat it as a recurring secondary signal source that helps widen candidate discovery and verify whether a topic is already surfacing in the Chinese practitioner community. Do not let it replace the primary source.
- `橘鸦AI早报 RSS` (`https://imjuya.github.io/juya-ai-daily/rss.xml`): fixed machine-readable cross-check lane. Useful for discovering which topics have already been condensed into a Chinese daily roundup, but still treat it as a secondary lane rather than first-party evidence.

Until the user curates a fixed Zhihu whitelist, start from dynamic search terms from the day's RSS hot topics, then widen with these fallback query clusters and keep only authors with clear background, long-form original judgment, and concrete evidence:

- `site:www.zhihu.com/people/ ("AI Agent" OR "智能体") ("工程" OR "工作流" OR "实践")`
- `site:zhuanlan.zhihu.com ("大模型" AND ("产品" OR "工程" OR "落地"))`
- `site:www.zhihu.com ("Claude Code" OR "Cursor" OR "Gemini CLI" OR "MCP") ("回答" OR "文章")`
- `site:www.zhihu.com ("多模态" OR "视频生成" OR "语音模型") ("实测" OR "对比" OR "踩坑")`
- `site:www.zhihu.com ("企业 AI" OR "AI 出海" OR "AI 应用落地") ("案例" OR "复盘" OR "观察")`
- `"橘鸦Juya" "AI 日报" site:zhihu.com`
- `"橘鸦Juya" "<daily-hot-topic>" site:zhihu.com`

Working rules for Zhihu:

- Prefer answers / articles written by engineers, researchers, PMs, founders, operators, or investors who show direct experience.
- De-prioritize 热榜总结、情绪判断、搬运整理、营销软文、以及只复述公开新闻的短回答。
- Prefer authors who repeatedly write about the same lane over one-off viral posts.

## Newsletter / Blog Priority Seeds

- `Latent Space` (`https://www.latent.space`): AI engineering framing and early trend vocabulary.
- `Import AI` (`https://jack-clark.net`): research, policy, and frontier-lab context.
- `One Useful Thing` (`https://www.oneusefulthing.org`): product/work pedagogy, adoption patterns, and real-world usage signal from Ethan Mollick.
- `Simon Willison's Blog` (`https://simonwillison.net`): practical LLM engineering and daily experiments.
- `Hugging Face Blog` (`https://huggingface.co/blog`): model, open-source, and product-layer updates with real technical detail.
- `Sebastian Raschka / Ahead of AI` (`https://magazine.sebastianraschka.com`): strong longform technical breakdowns on model architecture and training.
- `LangChain Blog` (`https://blog.langchain.com`): agent workflow, orchestration, and runtime product changes.
- `PyTorch Blog` (`https://pytorch.org/blog`): framework-level releases and research-to-production tooling.
- `NVIDIA Blog` (`https://blogs.nvidia.com`): hardware / inference / enterprise deployment changes that shape the AI stack.
- `Ollama Blog` (`https://ollama.com/blog`): local model packaging and developer workflow changes.
- `Gwern's Blog` (`https://gwern.net`): deep long-horizon analysis and predictive framing.
- `The Batch` (`https://www.deeplearning.ai/the-batch/`): broad but often useful synthesis with real judgment.
- `Interconnects` (`https://www.interconnects.ai`): Nathan Lambert on RLHF, post-training, and model behavior.
- `Lilian Weng's Blog` (`https://lilianweng.github.io`): deep technical essays and high-signal conceptual framing.

## Community RSS Seeds

- `Hacker News front page` (`https://news.ycombinator.com/rss`): high-signal English engineering/product discussion for daily hot-topic generation.
- `Lobsters` (`https://lobste.rs/rss`): slower but high-quality developer discussion; useful when HN gets too launch-heavy.
- `LINUX DO latest` (`https://linux.do/latest.rss`): high-velocity Chinese practitioner chatter, tooling pain points, and workflow changes.
- `LINUX DO top` (`https://linux.do/top.rss`): slower-moving but cleaner consensus / hot-topic ranking.
- `Reddit /r/LocalLLaMA top/new` (`https://old.reddit.com/r/LocalLLaMA/top/.rss?t=day`, `https://old.reddit.com/r/LocalLLaMA/new/.rss`): open-source model, inference stack, and local deployment topics.
- `Reddit /r/MachineLearning top` (`https://old.reddit.com/r/MachineLearning/top/.rss?t=day`): papers, engineering problems, and research-community discussion.
- `Reddit /r/ClaudeAI top` (`https://old.reddit.com/r/ClaudeAI/top/.rss?t=day`): Anthropic / Claude workflow and product-adoption chatter.
- `Reddit /r/OpenAI top` (`https://old.reddit.com/r/OpenAI/top/.rss?t=day`): ChatGPT / Codex / GPT workflow changes, pricing chatter, and user-facing breakpoints.
- `Reddit /r/singularity top` (`https://old.reddit.com/r/singularity/top/.rss?t=day`): broader frontier-model discourse and product diffusion signals.
- `橘鸦AI早报 RSS` (`https://imjuya.github.io/juya-ai-daily/rss.xml`): Chinese daily roundup feed with full-text `content:encoded`, useful as a fixed cross-source lane alongside dynamic Zhihu search.
- `GitHub releases Atom` (`vLLM`, `Transformers`, `SGLang`, `llama.cpp`, `Ollama`, `Open WebUI`, `LangChain`, `LlamaIndex`, `openai-python`, `anthropic-sdk-python`, `LiteLLM`): machine-readable shipping lane for runtime, tooling, SDK, and model-stack changes.

## Media Cross-Check Seeds

- `BBC Technology RSS` (`https://feeds.bbci.co.uk/news/technology/rss.xml`): broad but fast English technology reporting, useful as a second lane for policy / company / distribution moves.
- `BBC Business RSS` (`https://feeds.bbci.co.uk/news/business/rss.xml`): useful for infrastructure deals, regulation, and capital / org changes that affect AI rollout.
- `IT之家 RSS` (`https://www.ithome.com/rss/`): broad Chinese tech news lane; keep only AI-relevant items and never treat it as a first-party source when an official link exists.

## Discovery Expectations

- Try to surface at least 4 X candidate URLs from this seed list or one-hop adjacent same-profile accounts in each run.
- Scan at least 3 recent longform pieces from this blog/newsletter list or similarly high-signal authors in each run.
- Scan at least 3 Zhihu candidate answers / articles from the seed queries or stable authors in the same profile.
- **Scan at least 2 Chinese domestic sources** (微信公众号、即刻、少数派) to ensure Chinese-perspective coverage and a more global view.
- Generate the day's manual search terms from the community RSS hotlist before freeform searching:
  - `linux.do/latest.rss`
  - `linux.do/top.rss`
  - `old.reddit.com` AI subreddit RSS feeds
- Use these sources to sharpen `硅谷风向词`, emerging concepts, technical interpretation, and early product/workflow shifts.
- Do not let these sources replace first-party fact checks for launches, metrics, or claims.
- **Global balance**: the final report should not be purely Silicon Valley news. If a Chinese company (e.g., 智谱、月之暗面、百川、零一万物、阿里通义、字节) has a significant release, it should compete on equal footing with Western releases.
