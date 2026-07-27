#!/bin/zsh
# 정적 JSON 생성(export) → 프론트 빌드. GitHub Pages 산출물은 frontend/dist.
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR" || exit 1
PY="$DIR/.venv/bin/python"
if [ -x "$PY" ]; then "$PY" -m tracker export; else echo "(.venv 없음 — export 건너뜀, 기존 dashboard.json 사용)"; fi
cd "$DIR/frontend"
npm ci || npm install
npm run build
echo "빌드 완료 → frontend/dist (public/data/dashboard.json 포함)"
