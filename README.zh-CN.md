# Lumi AI Daily

[English](README.md)

Lumi AI Daily 是 AI 日报生产流程的审查版快照，覆盖从热点发现、来源归档、正文生成、标题封面策略、Remotion 视频、微信 DOCX、Telegram 发布包到 B 站元数据的完整链路。

这个目录已经按更接近开源项目的方式重新组织，方便审查流程、定位模块边界、排查降级策略和路径耦合，而不是在调度器内部路径和历史产物里来回翻。

> 这是审查快照。当前正式定时任务仍然从 `/Users/dystopia/.openclaw/workspace` 读取生产脚本，所以查看或审查这个目录不会影响下一次自动运行。

## 目录结构

```text
lumi-ai-daily/
├── automation/              # 每日调度任务配置
├── src/
│   ├── pipeline/            # 总编排、发现、文本编译、QA、命令包装
│   ├── intelligence/        # 来源策略、写作规则、日报模板
│   ├── media/               # 新闻配图解析和封面制作
│   ├── video/               # Fish TTS、视频构建器、Remotion 模板
│   ├── publishing/          # Telegram、微信公众号 DOCX、B 站发布包
│   └── integrations/        # X reader、Tavily 搜索、图片生成辅助
├── config/                  # 运行策略和风格配置
├── assets/                  # BGM、Lumi 资产、视觉参考
├── samples/                 # 2026-04-28 的轻量运行样本
└── docs/                    # 架构说明、来源映射、审查清单
```

## 从这里开始

- 定时任务入口：
  - `automation/discovery-preflight/automation.toml`
  - `automation/production-build/automation.toml`
- 流水线总入口：
  - `src/pipeline/run_tech_daily_pipeline.py`
- 标题封面策略：
  - `src/intelligence/references/title-cover-playbook.md`
  - `docs/research/title-cover-benchmark-2026-04-28.md`
- 采集预飞：
  - `src/pipeline/tech_daily_prepare_discovery.py`
- 视频生成：
  - `src/video/scripts/build_tech_daily_video.py`
  - `src/video/remotion/src/`
- 发布包：
  - `src/publishing/scripts/render_publish_bundle.py`
  - `src/pipeline/wechat_docx_builder.py`

## 流程顺序

1. `automation/discovery-preflight` 运行每日候选发现预飞。
2. `src/pipeline/tech_daily_prepare_discovery.py` 生成候选池和搜索词。
3. `src/pipeline/tech_daily_text_compile.py` 与 `src/pipeline/ai_daily_llm_content.py` 生成事实报告和平台文案源。
4. `src/media/scripts/fetch_story_images.py` 解析每条新闻的真实来源配图。
5. `src/pipeline/run_tech_daily_pipeline.py` 先准备 imagegen 封面生成 brief，再编排封面、视频、QA 和发布包。
6. `src/video/scripts/build_tech_daily_video.py` 使用 Fish TTS 和 Remotion 渲染正式视频。
7. `src/publishing/scripts/render_publish_bundle.py` 生成 Telegram、微信公众号和 B 站发布文件。

## 文档

- `docs/architecture.md`：模块边界和数据流
- `docs/audit-checklist.md`：高价值审查清单
- `docs/source-map.md`：审查目录到生产源路径的映射
- `docs/research/title-cover-benchmark-2026-04-28.md`：标题与封面 benchmark 案例
- `docs/file-index.txt`：快照文件清单
- `docs/checksums.sha256`：快照 checksum

## 快照范围

刻意排除：

- `node_modules/`
- Remotion `.bundle*` 打包缓存
- 历史 `remotion/public/generated/` 媒体文件
- `__pycache__/` 和 `*.pyc`
- 体积较大的正式视频、图片、音频、DOCX 产物

保留为轻量证据：

- `samples/README.md`
- `docs/research/thumbnails/` 下的封面 benchmark 素材
