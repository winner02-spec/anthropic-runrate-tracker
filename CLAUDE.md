# CLAUDE.md — anthropic-runrate-tracker 지속 지침

이 프로젝트를 수정할 때 **항상** 지킬 규칙. (데이터 무결성이 최우선)

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
