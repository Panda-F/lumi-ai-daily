# Bilibili Browser Setup

Use this path when the target Bilibili account is a normal creator account without confirmed Open Platform upload access.

## Why this path exists

- Official Bilibili Open Platform upload APIs exist, but the onboarding path is not a reliable assumption for normal personal creators.
- For this workspace, the practical fallback is browser-assisted upload with a persistent OpenClaw browser profile.

## Browser profile

This workspace uses the OpenClaw browser profile named `openclaw`.

## Start the login / upload page

Run:

```bash
python3 /Users/dystopia/.openclaw/workspace/skills/daily-multi-platform-publisher/scripts/bilibili_browser_bootstrap.py
```

The script will:

- ensure the OpenClaw browser is running,
- open the Bilibili creator upload page,
- detect whether the page is showing login or the upload surface,
- print the next step.

## When login is required

- Log in using QR code or the account’s own safe login path.
- Do not paste passwords into local scripts.
- If Bilibili asks for captcha / risk verification, complete it manually.

## Upload payload

The publish bundle emits `bilibili-upload.json` with:

- title
- description
- tags
- video file
- preferred cover file
- dynamic text

That manifest is the handoff object for later browser automation.
