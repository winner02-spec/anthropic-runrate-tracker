#!/bin/zsh
# 매일 09:30 KST: health check + 이상 탐지(anomaly_queue). 외부 본문 재분석 없음(비용 0).
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
LOG="$DIR/logs/health.log"; mkdir -p "$DIR/logs"
echo "===== $(date '+%F %T') health =====" >> "$LOG"
"$PY" -m tracker health >> "$LOG" 2>&1 || echo "health 경고" >> "$LOG"
