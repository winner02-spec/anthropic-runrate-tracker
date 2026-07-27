# CLAUDE.md — frontier-ai-runrate-tracker 지속 지침

이 프로젝트를 수정할 때 **항상** 지킬 규칙. (데이터 무결성이 최우선)
다중 회사(Anthropic·OpenAI) 대시보드. 표시명 "Frontier AI Revenue Tracker". repo/디렉터리명은 아직 `anthropic-runrate-tracker`(rename 절차는 README 참고).

## 데이터 원칙 (절대 규칙)
1. **공식과 추정치를 섞지 않는다.** official / estimate / target / reported 는 분리된 시계열·플래그로 유지.
2. **Run-rate 를 실제 회계상 연간 매출과 동일시하지 않는다.** 지표 표시명은 "Revenue Run-rate".
3. **출처 없는 숫자를 만들지 않는다.** 원문 URL·근거문장이 확인된 것만 확정(confirmed). 아니면 `needs_review`.
   웹 검증 불가 시 샘플 숫자를 만들지 말 것.
4. **발표일(published_at)과 기준일(as_of_start/end)을 분리**한다. 불명확하면 월범위 + 불확실성 표시.
5. **qualifier(over/approximately/range/target/estimate/reported)를 보존**한다.
   `$30B 이상` 을 정확한 `$30B` 로 저장하지 않는다(value_low=30, value_high=null, qualifier=over).
6. **비밀키(.env, 토큰)를 커밋하지 않는다.** `.env.example` 만 커밋.
7. 기사에는 제목·날짜·URL·짧은 근거문장·구조화 숫자만 저장(전문 복제 금지).
8. **계정·주문·금융거래 기능은 절대 포함하지 않는다.** 유료 우회·로그인 우회 금지.

## 다중 회사 규칙 (절대 규칙)
M1. 모든 관측·집계는 **회사(company_id)별로 분리**한다. 지표·성장속도·비교·이상탐지는 회사끼리만 계산(회사간 섞지 않음).
M2. **월 매출을 12배 한 값을 ARR/공식 Run-rate 로 저장·표시하지 않는다.** 파생은 `is_derived=1, qualifier=derived, metric_type=derived_annualized_revenue, calculation_method=monthly_revenue_x12, is_official=0` + `derived_from_id` 로 원본과 연결하고 차트에서 별도 마커.
M3. **공식(연환산) 선에는 `metric_type ∈ {arr, revenue_run_rate}` 이고 `is_official=1, is_derived=0` 인 것만** 올린다(월매출·파생·외부추정 제외).
M4. **제품/파일럿 지표(ads pilot ARR 등)는 product_metrics(product_arr)** 로 저장하고 전사 ARR 로 승격하지 않는다. 사용자수·구독자수는 $ share 계산 대상 아님.
M5. **회사 공식 도메인이라는 이유만으로** 펀딩액·기업가치·사용자수를 회사 ARR 로 자동 승인하지 않는다.
M6. content_hash·semantic_key 는 **회사 slug 로 스코프**한다(`dedup.company_content_hash`, `dedup.semantic_key(slug, ...)`). 기존 해시는 migration 에서 `scoped_hash` 로 1회 래핑(재래핑 금지 플래그 `hash_scoped=v5`).
M7. 회사 추가/변경 시 `config/companies.yml` 만 수정(수집 로직과 분리). 일일 수집은 매일 08:30 KST 1회.

## 개발 원칙
9. 기능 수정 후 **테스트와 빌드를 실행**한다: `pytest -q` + `cd frontend && npm run lint && npm run typecheck && npm test && npm run build`.
10. **데이터 구조(스키마)를 바꿀 때 migration 과 문서를 함께** 수정한다(`tracker/database/schema.py`, `docs/data-methodology.md`).
11. **실제 launchd 등록·외부 발송(Telegram 실발송)·GitHub push 는 사용자 승인 전 실행하지 않는다.**
    기본은 dry-run / plutil 검증까지만.
12. Python 3.11+ 기준 유지(3.9 폴백 금지). 시간대 Asia/Seoul, 금액 표준 USD billion(원문 단위도 보존).

## 출처 등급
- A: Anthropic 공식(뉴스룸·펀딩 발표·경영진 원문) → 명확 run-rate 표현이면 자동 확정 가능.
- B: Reuters/Bloomberg/FT/WSJ/CNBC/The Information 등 → reported. 공식 원문 발견 시 그걸 우선.
- C: YipitData/Sacra 등 외부 추정 → Estimated 시계열 전용.
- D: X/LinkedIn/개인 블로그 → 자동 확정 금지, review queue 만.

## 자주 만지는 파일
- 수집 출처/키워드: `config/sources.yml`
- 추출 규칙: `tracker/extractors/`, 분류: `tracker/classifiers/`, 지표: `tracker/metrics/calc.py`
- 정적 JSON: `tracker/export/dashboard.py` → `frontend/public/data/dashboard.json`
- 대시보드 UI: `frontend/src/`
