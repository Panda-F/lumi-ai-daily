# Publish Auth Matrix

Updated for this workspace on **2026-04-17**.

## Current path order

1. Telegram
2. WeChat Official Account (`docx` import)
3. Bilibili

## Current recommendation by platform

### Telegram

- Preferred path: bundle handoff via bot/API delivery
- Why:
  - 当前工作流已经能稳定产出 `telegram.txt` 和 `telegram-send.json`
  - 适合内部或私域频道的稳定投递
- What the user must do:
  - 配置 bot token 或现有 Telegram channel config
  - 确认目标 chat id

### WeChat Official Account

- Preferred path: manual `docx` import
- Why:
  - 当前默认链路是最稳的
  - `wechat.docx` 已带封面和内联图片
- What the user must do:
  - 登录公众号后台
  - 导入生成好的 `wechat.docx`
  - 最终检查版式和引用链接

### Bilibili

- Preferred path: official API **if** the account can complete Open Platform onboarding; otherwise browser posting
- Why:
  - 普通创作者账号往往仍然更适合浏览器投稿
  - 但 repo 已保留 B站工具链
- Workspace implementation:
  - browser bootstrap: `scripts/bilibili_browser_bootstrap.py`
  - formal entrypoints: `scripts/tech-daily-text-compile`, `scripts/tech-daily-video-build`, `scripts/tech-daily-publish-bundle`
- What the user must do:
  - 若有开放平台资质，完成 OAuth / app 配置
  - 若没有，就使用浏览器登录投稿

## How to apply this matrix in this repo

- Draft generation is always safe to automate.
- Live posting should branch like this:
  - Telegram: bundle / bot delivery
  - WeChat Official Account: `wechat.docx` import
  - Bilibili: API first only when credentials exist, else browser
- The current best practical flow in this repo is:
  - `tech-daily-text-compile` 生成日报正文和 writer 输出
  - `tech-daily-video-build` 生成视频
  - `tech-daily-publish-bundle` 生成三平台发布包

## Removed From This Workflow

不再产出，也不再维护发布脚本：

- X
- 知乎
- 小红书
- YouTube
