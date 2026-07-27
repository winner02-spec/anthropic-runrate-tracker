#!/bin/zsh
# 수집 1회 실행(3시간 간격 launchd 용). 변경 시에만 dashboard.json 재생성됨(collect 내부).
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
LOG="$DIR/logs/collect.log"
mkdir -p "$DIR/logs"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then echo "$(date '+%F %T') .venv 없음 — python3.11 -m venv .venv 후 pip install -r requirements.txt" >> "$LOG"; exit 1; fi
echo "===== $(date '+%F %T') collect =====" >> "$LOG"
"$PY" -m tracker collect >> "$LOG" 2>&1 || echo "collect 경고" >> "$LOG"
