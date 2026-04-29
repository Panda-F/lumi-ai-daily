#!/bin/bash
# ============================================================
# X-Reader v2 — Quick Smoke Test
# Run this on your Mac to verify the new browser-based reader.
# It reads ONE tweet with conservative settings.
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
READER="$SCRIPT_DIR/x-reader.py"
RESULT_JSON="/tmp/x-reader-test-result.json"
TEST_URL="${1:-${X_READER_TEST_URL:-https://x.com/simonw/status/1984390532790153484}}"

echo "=== X-Reader v2 Smoke Test ==="
echo ""

# 1. Check playwright is installed
echo "[1/3] Checking playwright…"
if ! python3 -c "from playwright.sync_api import sync_playwright; print('  ✓ playwright available')" 2>/dev/null; then
    echo "  ✗ playwright not found. Installing…"
    python3 -m pip install --user playwright
    python3 -m playwright install chromium
    echo "  ✓ installed"
fi

# 2. Read a single public tweet
echo ""
echo "[2/3] Reading a single tweet: $TEST_URL"
echo "       (browser window will open — IMPORTANT: if you're not logged into X,"
echo "        you'll need to log in manually in the opened window, then close it"
echo "        when prompted to continue)"
echo "       (pass a live status URL as the first argument if this test URL expires)"
echo ""

python3 "$READER" \
    --out "$RESULT_JSON" \
    --min-delay 3 \
    --max-delay 5 \
    "$TEST_URL"

echo ""
echo "[3/3] Result saved to $RESULT_JSON"
echo ""

# Quick validation
python3 -c "
import json, sys
try:
    data = json.load(open('$RESULT_JSON'))
    if isinstance(data, list):
        data = data[0]
    if data.get('error'):
        print('⚠️  Got error:', data['error'])
        print('   Possible cause: X login expired, tweet deleted, or the URL is stale.')
        sys.exit(1)
    print('✅ Success!')
    print(f'   Author:  {data.get(\"author\", \"?\")} (@{data.get(\"username\", \"?\")})')
    print(f'   Text:    {data.get(\"focal_text\", \"\")[:100]}…')
    print(f'   Likes:   {data.get(\"likes\", 0)}')
    print(f'   Thread:  {data.get(\"thread_count\", 0)} continuation replies')
    print(f'   Source:  {data.get(\"source\", \"?\")}')
except Exception as e:
    print(f'❌ Failed to parse result: {e}')
    sys.exit(1)
"

echo ""
echo "If you see ✅ above, the new x-reader is working. You can now run the daily report."
