# Browser profile setup (local, user-owned)

Goal: let OpenClaw's browser session reuse your already logged-in Chrome profile so it can open Gemini / ChatGPT / Sora as you.

## What you need from the user

- The path to their Chrome **User Data Directory**.
  - macOS (typical): `~/Library/Application Support/Google/Chrome`
  - If they use Chromium/Arc/Brave, the path differs.

- Which **profile** is logged in (e.g., `Default`, `Profile 1`).

## Constraints

- Profile reuse only works if the browser runner is allowed to read that directory.
- If the site prompts for login/2FA, the user must complete it.

## Verification checklist

1. Open `gemini.google.com` and confirm Gemini image generation/editing is available.
2. Open `chatgpt.com` and confirm ChatGPT Plus is logged in.
3. Open `sora.com` and confirm Sora can generate.
4. Confirm downloads land in `~/Downloads/` (or provide the configured download directory).
