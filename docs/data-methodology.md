# 데이터 방법론

## 지표 정의
- **Revenue Run-rate**: 특정 시점의 연환산 매출 속도. 회계상 실제 연간 매출(GAAP revenue)과 다르다.
- **metric_scope**: `company`(전사 Anthropic) / `product`(Claude Code 등).
- **qualifier**: 숫자 표현의 성격 — `exact` / `approximately`(약) / `over`(이상) / `range`(범위) /
  `target`(목표) / `estimate`(외부추정) / `reported`(보도). 저장 시 값(value_low/high)과 함께 보존.
- **published_at** vs **as_of**: 게시/발표일과 숫자가 가리키는 기준시점. 다르면 분리 저장하고,
  기준일이 불명확하면 월범위 + `uncertain` 표시.

## 출처 등급(source tier)
| 등급 | 예 | 처리 |
|---|---|---|
| A | Anthropic 공식(뉴스룸·펀딩 발표·경영진 원문) | 명확 run-rate 표현이면 **자동 확정** 가능 |
| B | Reuters·Bloomberg·FT·WSJ·CNBC·The Information | reported. 공식 원문 발견 시 그것을 우선 출처로 |
| C | YipitData·Sacra 등 외부 추정 | **Estimated 시계열 전용**(공식에 섞지 않음) |
| D | X·LinkedIn·개인 블로그·불명확 재인용 | 자동 확정 금지, **review queue** 만(원출처 확인 후 승격) |

## 데이터 승인 기준
- 확정(confirmed): 원문 URL + 근거문장 + 기준일이 있고, 자동확정 조건(Tier A·명확 run-rate) 충족하거나
  사람이 `approve` 한 경우.
- 검토(needs_review): 위 조건 미충족(Tier B/C/D, 기준일 불명확, 신뢰도 낮음 등).
- 거절(rejected): 오판·중복·무관.

## 중복 처리
- **content_hash**: canonical URL + 정규화 제목 + 발표일 + 값 + qualifier + 근거문장 → 동일 기사/추출 재수집 방지.
- **semantic_key**: 값 + 기준시점 + 공식여부 → 같은 공식 발표를 여러 매체가 재인용해도 새 포인트로 중복 추가하지 않음.

## 성장 속도(Growth Velocity)
- **공식 수치끼리만** 계산: `현재 - 직전`, 경과일수, 30일 환산, implied monthly growth.
- 두 점 중 하나라도 `over/approximately/range/target` 이면 `is_approximate=true` + "하한/범위 기준" 라벨.

## 가속(Acceleration)
- 최근 구간 속도(30일 환산) vs 직전 구간 속도 비교 → accelerating / stable / decelerating / insufficient_data(공식 3개 미만).

## 목표 진척(Target Progress)
- 목표(is_target)와 실제 공식값 분리. 목표 하단/상단 대비 %, 목표일까지 남은 기간, 조기 초과 여부.

## 밸류에이션 멀티플
- 동일/최근접 시점의 **공식** 기업가치와 **공식** Run-rate 사용: `valuation / run-rate`.
- 추정 기준 멀티플은 별도 표기. 두 값의 기준일 차이가 크면(기본 120일 초과) `date_mismatch_warning`.

## 제품 기여(Product Contribution)
- `제품 Run-rate / 전체 Anthropic Run-rate`. 두 숫자의 기준일이 다르면 경고(date_mismatch).

## 외부 추정치 — 기관별 분리
- 외부 추정(third_party_estimate)은 **기관(source_name)별로 별도 시계열**로 다룬다. TickerTrends·Sacra·Yipit·Funda 를 하나의 선으로 잇지 않는다.
- `latest_estimates_by_source`: 기관별 최신 추정 1건씩(기준일 최신순). `estimate_divergence`: 기관 간 최고/최저·편차(어느 쪽이 옳은지는 판단하지 않음).
- 원자료·산정 방법·기준일이 공개되지 않은 추정은 `date_precision=unknown` + `verification_status=provisional` 로 저장하고 **'추정 후보'** 로만 표시한다(차트에서는 선 없이 마커, 카드에는 "기준일 미상").

## 이상 탐지(anomaly_queue)
- 이상은 **자동 삭제·수정하지 않는다.** 정리는 status 로만 한다: `open` → `dismissed`(오탐) / `superseded`(중복) / `reviewed`.
  정리 시 `dismiss_reason`·`dismissed_at`·`superseded_by` 와 함께 **원 탐지값을 `audit_json` 에 보존**한다.
- **비교 범위**: `estimate_drop`(추정 하락)은 `company_id` · `metric_type` · `source_name`(=산정기관/방법론 시계열) 이 모두 같고
  **기준일이 명확한**(`date_precision != unknown`) observation 끼리만 판정한다. 기관이 다른 값의 차이는 하락이 아니다.
- **기관 간 격차**는 오류가 아니라 안내용으로 `estimate_dispersion`(기본 임계 20%) 으로 분리 기록한다.
- **재계산 중복 방지**: `anomaly_key = company_id | anomaly_type | metric_type | source | 기준 observation id` 로 같은 이상을 같은 행에 묶는다.
  값·경과일처럼 매 실행 바뀌는 값은 key 에 넣지 않고, 재탐지 시 `detail` · `last_seen_at` · `age_days` · `occurrence_count` 만 갱신한다(새 행 생성 없음).
  이미 `dismissed`/`superseded` 인 건은 재계산해도 다시 `open` 으로 되살리지 않는다.
- 소유 회사(`company_id`)는 탐지 시점에 기록한다. 레거시 오분류는 detail 문자열이 아니라 **연결 observation 재확인**으로만 정정하고
  (`scripts/migrate_anomaly_ownership.py`), 정정 이력을 `audit_json`(original/corrected/correction_reason/corrected_at/evidence)에 남긴다.

## 한계·주의
- 공개 데이터 기반이라 최신 공식 수치와 시차가 있을 수 있음.
- Run-rate 는 연환산 스냅샷 — 회계 매출이 아님.
- 외부 추정치는 업체별 방법론 차이가 큼 → 공식과 절대 합산·연결하지 않음.
- qualifier 가 붙은 값은 정밀 단일값으로 해석하지 말 것.
