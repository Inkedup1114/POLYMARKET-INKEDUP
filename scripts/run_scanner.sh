#!/usr/bin/env bash
set -e
source .venv/bin/activate
python -m inkedup_bot.cli scan --interval "${1:-15}"
