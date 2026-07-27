# Frontier AI Revenue Tracker

**Anthropic·OpenAI**의 **공식 Revenue Run-rate/ARR**와 외부 추정치·목표·밸류에이션·제품지표를
출처 등급별로 수집·검증·저장하고, 방향/가속/공식–추정 갭/목표 진척/밸류에이션 멀티플·회사간 비교를
계산해 **한국어 대시보드**로 제공하는 투자용 트래커. 상단 탭: **비교 / Anthropic / OpenAI**(기본=비교).

> ⚠️ **Revenue Run-rate ≠ 회계상 연간 매출.** 공식/추정 시계열은 절대 섞지 않고 분리 표시합니다.
> 월 매출을 12배 한 **파생 연환산값**은 공식 ARR 로 표시하지 않습니다(별도 마커).
> 숫자는 원문·근거문장이 확인된 것만 확정하며, 검증 못한 값은 `needs_review` 로 남깁니다.

## 다중 회사 구조
- `companies` 테이블 + 관련 8개 테이블 `company_id` FK. 기존 Anthropic 데이터는 migration 으로 보존.
- 회사별 수집 설정: `config/companies.yml`(검색어·소스·mention_terms). anthropic 은 `config/sources.yml` 레거시 폴백.
- content_hash·semantic_key 에 회사 slug 포함 → 서로 다른 회사의 같은 숫자가 중복 처리되지 않음.
- metric_type 세분화: `arr · revenue_run_rate · monthly_revenue · derived_annualized_revenue · product_arr · target · valuation · active_users · paid_subscribers · business_customers`.
- CLI 회사 지정: `python -m tracker collect --company openai|anthropic|all`, `add-manual --company ...`.

## repo 이름 변경 절차(후속, 지금은 미실행)
후보명 **`frontier-ai-runrate-tracker`**. 이름/리모트는 기능·테스트 안정화 후 변경한다. 변경 시 **함께 수정**:
1. GitHub repo rename → `git remote set-url origin git@github.com:<owner>/frontier-ai-runrate-tracker.git`
2. **Vite base path** (`frontend/vite.config.ts` 의 `base`)를 `/frontier-ai-runrate-tracker/` 로.
3. **GitHub Actions** (`.github/workflows/deploy.yml`)의 경로·아티팩트 참조 확인.
4. **GitHub Pages URL** 변경 반영: `https://<owner>.github.io/frontier-ai-runrate-tracker/`.
5. README·문서의 URL, launchd/scripts 경로(`~/market-bots/anthropic-runrate-tracker`) 갱신.

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
cp launchd/com.anthropic-runrate.daily.plist           ~/Library/LaunchAgents/
cp launchd/com.anthropic-runrate.weekly-backfill.plist ~/Library/LaunchAgents/
cp launchd/com.anthropic-runrate.health.plist          ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.anthropic-runrate.daily.plist
launchctl load ~/Library/LaunchAgents/com.anthropic-runrate.weekly-backfill.plist
launchctl load ~/Library/LaunchAgents/com.anthropic-runrate.health.plist
```
- 매일 08:30(daily+discovery) / 매주 일 09:00(backfill) / 매일 09:30(health). **3시간 수집 폐지.** 전제: `.venv`. 상세는 아래 v0.2 참고.

## 오류 복구
- 수집 실패는 종목/소스별로 격리되어 나머지는 계속. 로그: `logs/`.
- `python -m tracker status` 로 마지막 수집/검토 대기 확인.
- dashboard 깨짐 시 `python -m tracker export` 재실행.

## 데이터 해석 주의사항
- **Run-rate 는 연환산 지표**로, 회계상 실제 연간 매출과 다름.
- `over`/`approximately`/`range` qualifier 는 정밀 단일값이 아님(라벨 표시).
- 공식 성장률은 **공식끼리만** 계산. 추정치는 별도 시계열.
- 발표일(published_at)과 기준일(as_of)은 다를 수 있음(UI에 분리 표시).

---

## v0.2 개선 (수집 자동화·과거 복원·비용절감)

### 수집 CLI
```sh
python -m tracker collect --mode daily       # 최근 7일 신규 자료(공식·매체·추정), ETag/content-hash 캐시 스킵
python -m tracker collect --mode discovery   # 새 도메인 탐색 → source_candidates(자동승격 X)
python -m tracker backfill --from 2024-01-01 --to today [--source official|reuters|estimates] [--dry-run]
python -m tracker verify-history [--record]  # 누락구간·중복·날짜역전·상충·혼입·qualifier손실·재인용중복
python -m tracker health                     # 마지막수집·파서오류·review적체·이상탐지(anomaly_queue)·배포준비
```
- backfill 원문 목록: `config/backfill_sources.yml` (검증 등급별: official=직접확인 / reuters=다수매체 보도 / estimates_*=외부추정).
- 재실행해도 중복 0 (content_hash + semantic_key 이중 dedup).

### source_type 체계 (공식/추정 분리)
`official_current`(공식 현재값) · `official_retrospective`(공식 회고 과거값) · `reported`(매체 자체보도) ·
`reported_company_statement`(매체가 회사발언 재인용) · `third_party_estimate`(TickerTrends/Yipit/Sacra) · `target`.
공식·보도·추정은 대시보드에서 별도 시계열로 표시하며 하나의 선으로 연결하지 않음.

### 실행 스케줄 (launchd, 등록은 수동 승인 후)
- **3시간 incremental 수집은 폐지**(run-rate 는 장중 데이터 아님).
- 매일 08:30 KST: `com.anthropic-runrate.daily`(daily+discovery)
- 매주 일 09:00 KST: `com.anthropic-runrate.weekly-backfill`
- 매일 09:30 KST: `com.anthropic-runrate.health`(이상탐지)
- 등록: `cp launchd/*.plist ~/Library/LaunchAgents/ && launchctl load ...` (승인 후). plutil 검증 완료.

### 비용·토큰 정책 (item 11)
- **기본 수집·파싱은 Python 규칙기반만 사용 → 토큰 0.** LLM 분류는 `config/settings.yml` `llm.enabled=false` 기본 OFF.
- LLM은 (1) `llm.enabled=true` 로 켜고 (2) `only_on_new_candidates=true` → **신규 숫자 후보가 있을 때만** 호출, batch 분류.
- `ANTHROPIC_API_KEY` 없어도 전체 파이프라인 정상 동작.
- **재분석 안 함**: 같은 URL·content_hash·ETag·Last-Modified → `fetch_cache` 로 스킵.
- **데이터 변경 없으면 export/build/배포 준비 생략**(`write_if_changed`, schema_meta.data_fp 지문 비교).
- API 호출 수·추정 토큰은 `ingestion_runs.api_calls/est_tokens` 에 기록. 현재 기본 설정에서 실제 호출 0.
- health check 는 외부 기사 본문을 재분석하지 않음(비용 0).

### 외부 추정치(TickerTrends/Yipit)
- `estimates.auto_approve=false`(기본). 이미지/OCR·원문 URL 미확인 → **needs_review**(공식 시계열에 절대 미혼입).
- 원문 URL 확인 후에만 approved 가능. TickerTrends 와 Yipit 은 서로 별도 시계열.

### 피드백 재사용 (재훈련 아님)
- approve/reject 시 `classification_feedback` 저장. 과거 오분류/거절 이력 있는 도메인은 자동확정을 막고 review 로.
- 단, **사용자 피드백만으로 외부추정을 공식으로 승격하지 않음**(공식여부는 원출처·근거 우선).

### 검색 색인 억제 (item 14, 접근통제 아님)
- `frontend/index.html` 에 `robots/googlebot noindex,nofollow,noarchive,nosnippet` → 빌드 산출물 `dist/index.html` 에도 포함. sitemap 미생성.

### 코드 변경 vs 데이터 변경
- 데이터 변경: 자동 export·배포 준비 가능. 코드 변경: **자동 main push 안 함** — diff·테스트 후 사용자 승인 시 push.
