#!/bin/zsh
# 매일 08:30 KST: 최근 7일 신규 자료 수집(daily) + 새 출처 탐색(discovery). 전 회사(--company all).
# 데이터가 실제 변경될 때만 export(변경감지). LLM 미사용(규칙 기반). 3시간 수집은 폐지됨.
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
LOG="$DIR/logs/daily.log"; mkdir -p "$DIR/logs"
echo "===== $(date '+%F %T') daily =====" >> "$LOG"
"$PY" -m tracker collect --mode daily     --company all >> "$LOG" 2>&1 || echo "daily collect 경고" >> "$LOG"
"$PY" -m tracker collect --mode discovery --company all >> "$LOG" 2>&1 || echo "discovery 경고" >> "$LOG"
# collect 내부에서 변경 시에만 export 됨. (Telegram 은 dry-run 만; 실발송은 승인 후)
