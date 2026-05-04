# Lumi AI Daily

[English](README.md)

Lumi AI Daily 是每日 AI 日报流程的可审查代码仓库。现在主线只保留三件事：采集最新高质量信息和真实配图，生成微信公众号/B 站/视频文案，渲染 Remotion 视频、微信公众号 DOCX 和 B 站元数据。

## 目录结构

```text
lumi-ai-daily/
├── automation/              # 每日定时任务配置
├── src/
│   ├── run_tech_daily_pipeline.py
│   ├── common/              # 路径、报告模型、来源/标题工具
│   ├── discovery/           # 信息源采集和真实新闻配图采集
│   ├── content/             # 事实稿、内容编译、微信公众号 DOCX
│   ├── visuals/             # 面向 imagegen skill 的封面 brief
│   ├── video/               # 视频脚本、TTS、BGM、B 站产物
│   ├── video/remotion/      # Remotion app 和渲染脚本
│   └── intelligence/        # 统一信息源策略和写作/标题/封面规则
├── config/                  # 运行风格配置
├── assets/                  # BGM、Lumi 形象、视觉参考
└── docs/                    # 架构说明和文件清单
```

## 主入口

- `automation/discovery-preflight/automation.toml`
- `automation/production-build/automation.toml`
- `src/run_tech_daily_pipeline.py`
- `src/intelligence/source_policy.toml`
- `src/discovery/prepare_discovery.py`
- `src/content/compile_content.py`
- `src/content/render_wechat.py`
- `src/visuals/prepare_cover_brief.py`
- `src/video/build_video.py`
- `src/video/render_bilibili.py`

## 主流程

1. `discovery/prepare_discovery.py` 从 `src/intelligence/source_policy.toml` 读取信息源和关键词，采集当天 AI 热点。
2. `content/build_report.py` 在日报输入缺失时生成事实稿。
3. `content/compile_content.py` 和 `content/llm_content.py` 生成公众号正文、视频文案、标题包和 B 站文案。
4. 每条新闻配图直接使用采集阶段的 source/reference pack；缺真实图时微信公众号 DOCX 步骤失败，不再生成本地补图卡片。
5. `visuals/prepare_cover_brief.py` 生成封面 brief，封面只走 imagegen skill。
6. `video/build_video.py` 使用 Fish TTS 和 Remotion 生成视频。
7. `content/render_wechat.py` 输出微信公众号 DOCX；`video/render_bilibili.py` 输出 B 站文件。

每天产物目录只保留两个顶层文件夹：`process/` 放过程产物，`final/` 放标题命名的视频、封面、唯一一份 DOCX、字幕和 B 站元数据。

## 文档

- `docs/architecture.md`：当前模块边界和数据流
- `docs/code-file-index.tsv`：逐个代码文件的中文说明
- `docs/file-index.txt`：仓库文件清单
- `docs/checksums.sha256`：当前 checksum
