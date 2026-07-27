#!/bin/zsh
# 매주 일요일 09:00 KST: 2024년 이후 과거 자료 재검사(backfill). 재실행 중복 0.
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
LOG="$DIR/logs/backfill.log"; mkdir -p "$DIR/logs"
echo "===== $(date '+%F %T') weekly backfill =====" >> "$LOG"
"$PY" -m tracker backfill --from 2024-01-01 --to today >> "$LOG" 2>&1 || echo "backfill 경고" >> "$LOG"
"$PY" -m tracker verify-history --record             >> "$LOG" 2>&1 || echo "verify 경고" >> "$LOG"
