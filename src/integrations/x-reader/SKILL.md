---
name: x-reader
description: Read X (Twitter) posts using the user's logged-in browser profile via Playwright. Supports single and batch reads, thread continuation, and reply-context capture with built-in anti-ban safeguards.
version: 2.0.0
author: OpenClaw
license: MIT
tags: [twitter, x, social-media, browser, playwright]
requirements:
  - Python 3.10+
  - playwright (auto-installed on first run)
  - A Chrome/Chromium profile with an active X login
install: |
  pip install playwright
  python3 -m playwright install chromium
---

# X-Reader v2

Read X (Twitter) posts using the user's own logged-in browser session.

Replaces the old RapidAPI + Nitter approach (both broken as of 2026-04).

## Anti-Ban Safety

This tool is designed to protect the user's X account:

- **Hard cap**: max 15 URLs per invocation (cannot be overridden)
- **Human-like delays**: 5–12 seconds (configurable) between each page load
- **Read-only**: zero automated interactions — no likes, retweets, follows, or DMs
- **Individual pages only**: only navigates to `/status/` URLs, never timelines or search
- **Real profile**: uses the user's actual browser cookies and session, not a bot fingerprint
- **Visible browser**: runs non-headless by default so the user can monitor activity

## Usage

### Single tweet

```bash
python3 x-reader.py "https://x.com/karpathy/status/2026731645169185220"
```

### Batch mode (for daily report source verification)

```bash
# urls.txt: one tweet URL per line
python3 x-reader.py --batch urls.txt --out results.json
```

### Smoke test / diagnostics

```bash
bash test_x_reader.sh "https://x.com/simonw/status/1984390532790153484"
python3 debug_x_reader.py "https://x.com/simonw/status/1984390532790153484"
```

### Custom delays (for extra caution)

```bash
python3 x-reader.py --min-delay 10 --max-delay 20 "https://x.com/..."
```

## Output Format

```json
{
  "id": "2026731645169185220",
  "text": "Full tweet text including thread continuation…",
  "focal_text": "Just the main tweet text",
  "thread_count": 2,
  "reply_context_count": 4,
  "reply_contexts": [
    {
      "author": "Jane Doe",
      "username": "janedoe",
      "text": "High-signal reply text…",
      "created_at": "2026-04-08T15:35:00.000Z",
      "likes": 120
    }
  ],
  "author": "Andrej Karpathy",
  "username": "karpathy",
  "created_at": "2026-04-08T15:30:00.000Z",
  "likes": 1200,
  "retweets": 340,
  "replies": 89,
  "quotes": 45,
  "media_urls": ["https://pbs.twimg.com/media/..."],
  "url": "https://x.com/karpathy/status/2026731645169185220",
  "source": "browser"
}
```

## Integration with ai-daily-intel

The daily report skill should call x-reader in batch mode for all candidate X URLs:

1. Collect candidate X URLs during the discovery phase.
2. Write them to a temporary file (one per line).
3. Run `python3 x-reader.py --batch <file> --out <results.json>`.
4. Parse results — any entry with an `"error"` key means the tweet was unreadable.
5. For unreadable tweets, fall back to `web_search` snippet for the exact status URL.

Successful entries now also expose:

- `text_chars`: non-whitespace body length
- `duplicate_key`: stable `x:<tweet_id>` key for hot-window dedup
- `extraction_confidence`: heuristic confidence score for downstream filtering
- `reply_context_count` + `reply_contexts`: high-signal non-author replies shown on the status page, kept separate from focal tweet text

## Error Handling

- If the returned JSON has `"error"`, the tweet could not be extracted.
- A read is only considered successful when the focal tweet text and the expected username both match the requested status URL.
- Common causes: deleted tweet, suspended account, login expired, rate limited.
- The smoke-test and debug helpers both accept a live status URL argument; use that when the default test tweet ages out.
- When unreadable, fall back to a search snippet rather than quoting empty data.
- If login has expired, the user should re-login in the openclaw browser profile.

## Notes

- The reader reuses cookies from the user's real browser login rather than automating the default Chrome profile.
- Thread detection automatically captures up to 3 same-author continuation posts.
- Reply-context capture keeps up to 6 visible non-author replies as separate context so downstream scoring can read the discussion without polluting the focal tweet body.
