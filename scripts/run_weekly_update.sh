#!/bin/zsh
# 매주 일요일 09:00 KST — 주간 데이터 갱신 파이프라인.
#   수집 → backfill → verify-history → 이상 재계산 → export → 테스트 → (변경 있을 때만) main push
# 실패하면 push 하지 않는다. 데이터 변경이 없으면 커밋·push 도 하지 않는다.
set -uo pipefail
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
# launchd 는 PATH 가 /usr/bin:/bin:/usr/sbin:/sbin 뿐이라 node/npm 을 찾지 못한다 → 보강
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
[ -f "$DIR/.env" ] && set -a && source "$DIR/.env" && set +a
mkdir -p "$DIR/logs"
LOG="$DIR/logs/weekly_update.log"
say() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }

say "===== weekly update 시작 ====="
# ① 신규 자료 수집(Anthropic·OpenAI 전 회사) + ② 새 출처 discovery
"$PY" -m tracker collect --mode daily --company all     >> "$LOG" 2>&1 || say "collect(daily) 경고"
"$PY" -m tracker collect --mode discovery --company all >> "$LOG" 2>&1 || say "collect(discovery) 경고"
# ③ 과거 시계열 backfill (content_hash·semantic_key 로 중복 제거 — 재실행 시 신규 0)
"$PY" -m tracker backfill --from 2024-01-01 --to today  >> "$LOG" 2>&1 || say "backfill 경고"
# ④ 이력 검증(날짜 역전·중복 재인용·qualifier 손실 등)
"$PY" -m tracker verify-history --record     >> "$LOG" 2>&1 || say "verify-history 경고"
# ⑤ 이상 재계산(anomaly recompute — dismissed/superseded 는 되살리지 않음)
"$PY" -m tracker health                      >> "$LOG" 2>&1 || say "health 경고"
# ⑥ provenance audit (실패하면 export 자체가 중단됨 — 여기서 먼저 명시적으로 확인)
"$PY" - <<'PYEOF' >> "$LOG" 2>&1 || { say "provenance audit 실패 — 중단"; exit 1; }
from tracker import config
from tracker.database import db
from tracker.export import dashboard
dashboard.validate_provenance(db.connect(str(config.DB_PATH)))
print("provenance audit PASS")
PYEOF
# ⑦ dashboard.json export
"$PY" -m tracker export                      >> "$LOG" 2>&1 || { say "export 실패 — 중단"; exit 1; }

# 검증: 파이썬 테스트 + 프론트 빌드 파이프라인. 하나라도 실패하면 push 하지 않는다.
"$PY" -m pytest tests/ -q                    >> "$LOG" 2>&1 || { say "pytest 실패 — push 중단"; exit 1; }
if command -v npm >/dev/null 2>&1; then
  ( cd "$DIR/frontend" && npm run lint && npm run typecheck && npm test && npm run build ) \
      >> "$LOG" 2>&1 || { say "frontend 검증 실패 — push 중단"; exit 1; }
fi

# 데이터·코드 변경이 있을 때만 커밋 & push (dashboard.json 만 바뀌어도 배포 가치 있음)
if [ -z "$(git -C "$DIR" status --porcelain)" ]; then
  say "변경 없음 — 커밋·push 생략"
else
  git -C "$DIR" add -A
  git -C "$DIR" commit -q -m "chore(weekly): refresh dashboard data $(date '+%F')" >> "$LOG" 2>&1
  git -C "$DIR" push origin main >> "$LOG" 2>&1 && say "push 완료(Pages 자동 배포)" || say "push 실패"
fi
say "===== weekly update 종료 ====="
