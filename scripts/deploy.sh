#!/bin/zsh
# GitHub Pages 배포. ※ 실제 배포는 사용자 승인 + repo 준비 후에만.
# 이 스크립트는 빌드까지 하고, 원격/gh-pages 가 준비돼 있을 때만 push 한다.
set -e
DIR="/Users/baeeunbin/market-bots/anthropic-runrate-tracker"
cd "$DIR"
zsh "$DIR/scripts/build_dashboard.sh"

if ! git -C "$DIR" rev-parse --git-dir >/dev/null 2>&1; then
  echo "git repo 아님 — 먼저: git init && git remote add origin <URL>"; exit 0
fi
if ! git -C "$DIR" remote get-url origin >/dev/null 2>&1; then
  echo "origin remote 없음 — GitHub repo 생성 후 remote 연결 필요. 배포 중단."; exit 0
fi

echo "GitHub Actions(.github/workflows/deploy.yml) 로 배포하거나, 아래로 수동 배포:"
echo "  (권장) main 에 push → Actions 가 frontend 빌드 후 Pages 배포"
git -C "$DIR" add -A
git -C "$DIR" commit -m "build: dashboard $(date '+%F')" || echo "변경 없음"
echo "다음: git push origin main  (실제 push 는 승인 후 직접)"
