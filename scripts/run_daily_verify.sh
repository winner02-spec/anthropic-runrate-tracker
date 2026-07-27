#!/bin/zsh
# 매일 08:30 KST 전체 재검증: 수집 + export(정적 JSON). 실패는 로그 기록.
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
LOG="$DIR/logs/daily.log"
mkdir -p "$DIR/logs"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then echo "$(date '+%F %T') .venv 없음" >> "$LOG"; exit 1; fi
echo "===== $(date '+%F %T') daily verify =====" >> "$LOG"
"$PY" -m tracker collect >> "$LOG" 2>&1 || echo "collect 경고" >> "$LOG"
"$PY" -m tracker export  >> "$LOG" 2>&1 || echo "export 실패" >> "$LOG"
