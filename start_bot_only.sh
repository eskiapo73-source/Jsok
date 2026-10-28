#!/usr/bin/env bash
set -e
if [ -f .env ]; then set -a; source .env; set +a; fi
exec python bot.py
