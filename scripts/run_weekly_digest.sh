#!/bin/zsh
# 매주 일요일 10:00 KST — 지정 텔레그램 채널 1곳에 주간 다이제스트 1회 게시.
#   · 대상 채널은 .env 의 TELEGRAM_CHAT_ID 하나로 고정(개인 DM·다른 대화로 보내지 않음)
#   · TELEGRAM_ENABLED=false 면 실제 발송 없이 dry-run 로그만 남는다
#   · 같은 주 재발송은 --force 를 붙였을 때만 (기본은 주차 키로 중복 차단)
set -uo pipefail
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
mkdir -p "$DIR/logs"
LOG="$DIR/logs/weekly_digest.log"
echo "[$(date '+%F %T')] weekly digest" >> "$LOG"
"$PY" -m tracker weekly-digest --send "$@" >> "$LOG" 2>&1 || echo "digest 실패" >> "$LOG"
