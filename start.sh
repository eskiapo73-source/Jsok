#!/usr/bin/env bash
set -e
# Load .env if present (local/Termux). On Render use Dashboard env vars.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
python bot.py &
BOT_PID=$!
# Render sets PORT; local default 8080
exec gunicorn -b 0.0.0.0:${PORT:-8080} api:app
