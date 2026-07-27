# Anthropic Revenue Run-rate Tracker

Anthropic의 **공식 Revenue Run-rate**와 외부 추정치·목표·밸류에이션·제품지표(Claude Code 등)를
출처 등급별로 수집·검증·저장하고, 방향/가속/공식–추정 갭/목표 진척/밸류에이션 멀티플을 계산해
**한국어 대시보드 + Telegram 알림**으로 제공하는 투자용 트래커.

> ⚠️ **Revenue Run-rate ≠ 회계상 연간 매출.** 공식/추정 시계열은 절대 섞지 않고 분리 표시합니다.
> 숫자는 원문·근거문장이 확인된 것만 확정하며, 검증 못한 값은 `needs_review` 로 남깁니다.

## 구조
```
tracker/            수집·검증·계산·export (Python 3.11+, SQLite)
  collectors/       RSS·Google News·공식 뉴스룸·seed·manual (사이트별 파서 격리)
  extractors/       숫자/qualifier/단위, 발표일·기준일 분리
  classifiers/      출처 등급(A~D), 공식/보도/추정/목표
  metrics/          run-rate·velocity·acceleration·target·multiple·product
  notifications/    Telegram(공식🟢/추정🟠/검토⚪, dry-run·중복방지)
  export/           SQLite → frontend/public/data/dashboard.json (비밀 없음)
  cli/              python -m tracker <command>
frontend/           Vite + React + TS 대시보드 (정적 JSON 소비 → GitHub Pages)
config/sources.yml  수집 출처·키워드·등급 매핑
data/seeds/         검증된 초기 데이터(CSV)
launchd/ scripts/ .github/workflows/  자동화(수집 3h·매일 08:30 재검증·Pages 배포)
docs/               methodology·operations
```

## 설치
```sh
# Python (3.11+ 필수 — 3.9 폴백 없음)
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # Telegram/Anthropic 키는 선택. 없어도 동작.

# 프론트엔드
cd frontend && npm install
```

## 실행
```sh
# 백엔드 (python -m tracker <command>)
python -m tracker init            # SQLite 생성
python -m tracker seed            # 검증된 초기 데이터 병합(중복 자동 방지)
python -m tracker collect         # 공개 소스 수집 → 자동확정/검토큐
python -m tracker review          # 검토 대기 후보 목록
python -m tracker approve <id>    # 후보 승인 → 확정 + dashboard 갱신
python -m tracker reject <id>     # 후보 거절
python -m tracker add-url <url>   # 수동 감시 URL 추가
python -m tracker add-manual --value 14 --source-url ... --evidence "..." --official
python -m tracker export          # dashboard.json 재생성
python -m tracker status          # 현황

# 프론트엔드
cd frontend
npm run dev        # 로컬 개발 서버
npm run build      # 프로덕션 빌드 → frontend/dist
npm test           # vitest
```

## 수동 데이터 추가 / 후보 승인
- 검증된 공식 숫자: `python -m tracker add-manual` (원문 URL·근거문장 필수, 없으면 `needs_review`).
- 자동 수집 후보: `python -m tracker review` 로 확인 → `approve`/`reject`.
- 초기 seed 는 `data/seeds/*.csv` 로 관리(재실행 중복 없음).

## GitHub Pages 배포
1. GitHub 에 repo 생성 후 `git remote add origin <URL>`.
2. repo Settings → Pages → Source = GitHub Actions.
3. `main` push 시 `.github/workflows/deploy.yml` 가 `frontend` 빌드 후 Pages 배포.
   (배포물은 커밋된 `frontend/public/data/dashboard.json` 사용)
- 정적 JSON·빌드 산출물만 배포. **DB·.env 는 배포/커밋되지 않음.**

## Telegram 설정
- `.env` 에 `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ENABLED=true`.
- 미설정/false 면 **dry-run**(콘솔 출력)으로 동작하며 수집·대시보드는 정상.
- 새 숫자/목표 발견 시에만 발송, 동일 내용 중복 발송 안 함.

## launchd 등록 (사용자 승인 후에만)
```sh
cp launchd/com.anthropic-runrate.collect.plist ~/Library/LaunchAgents/
cp launchd/com.anthropic-runrate.daily-verify.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.anthropic-runrate.collect.plist
launchctl load ~/Library/LaunchAgents/com.anthropic-runrate.daily-verify.plist
```
- 수집 3시간 간격 + 매일 08:30 KST 전체 재검증. 전제: `.venv` 생성.

## 오류 복구
- 수집 실패는 종목/소스별로 격리되어 나머지는 계속. 로그: `logs/`.
- `python -m tracker status` 로 마지막 수집/검토 대기 확인.
- dashboard 깨짐 시 `python -m tracker export` 재실행.

## 데이터 해석 주의사항
- **Run-rate 는 연환산 지표**로, 회계상 실제 연간 매출과 다름.
- `over`/`approximately`/`range` qualifier 는 정밀 단일값이 아님(라벨 표시).
- 공식 성장률은 **공식끼리만** 계산. 추정치는 별도 시계열.
- 발표일(published_at)과 기준일(as_of)은 다를 수 있음(UI에 분리 표시).
