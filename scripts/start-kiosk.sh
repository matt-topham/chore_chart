#!/usr/bin/env bash
set -euo pipefail

URL="${CHORE_URL:-http://localhost:5000}"

# Give the web service a moment to become reachable.
for _ in $(seq 1 30); do
  if curl -fsS "$URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

exec chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-pinch \
  --overscroll-history-navigation=0 \
  "$URL"
