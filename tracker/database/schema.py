# -*- coding: utf-8 -*-
"""SQLite 스키마 정의 + 간단 migration.

설계 원칙:
· 공식/추정/목표를 is_official/is_estimate/is_target 로 분리(같은 시계열로 섞지 않음).
· 숫자표현: value_low/high_usd_bn + qualifier 로 '$30B 이상' 등을 정확값처럼 저장하지 않음.
· 날짜: published_at(게시일) 과 as_of_start/end(기준시점) 분리.
· 중복: content_hash 로 동일 발표 재인용을 새 포인트로 추가하지 않음.
"""
from __future__ import annotations

SCHEMA_VERSION = 5

DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY, value TEXT
);

-- 다중 회사 레지스트리(Anthropic/OpenAI …). 관련 테이블은 company_id 로 이 표를 참조.
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT UNIQUE NOT NULL,   -- anthropic | openai
    display_name    TEXT NOT NULL,          -- Anthropic | OpenAI
    official_domain TEXT,                   -- anthropic.com | openai.com
    created_at      TEXT
);

-- 핵심: run-rate/매출 업데이트 (공식·보도·추정·목표 모두 여기, 플래그로 구분)
CREATE TABLE IF NOT EXISTS runrate_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company            TEXT NOT NULL DEFAULT 'Anthropic',  -- (레거시, 표시용) 권위값은 company_id
    company_id         INTEGER REFERENCES companies(id),
    metric_scope       TEXT NOT NULL,      -- company | product
    metric_type        TEXT NOT NULL,      -- arr|revenue_run_rate|monthly_revenue|derived_annualized_revenue|product_arr|target 등
    value_low_usd_bn   REAL,               -- USD billion 표준(하단)
    value_high_usd_bn  REAL,               -- 범위 상단(단일값이면 NULL)
    original_value     TEXT,               -- 원문 숫자 문자열(보존)
    original_currency  TEXT DEFAULT 'USD',
    original_unit      TEXT,               -- million | billion 등 원문 단위
    qualifier          TEXT NOT NULL,      -- exact|approximately|over|range|target|estimate|reported
    as_of_start        TEXT,               -- 기준시점 시작(YYYY-MM-DD)
    as_of_end          TEXT,               -- 기준시점 끝(불명확 시 월범위)
    date_precision     TEXT DEFAULT 'day', -- day | month_range | quarter | unknown (기준일 정밀도)
    display_date       TEXT,               -- 차트 위치용 단일일(원본 기준일 아님; 범위면 대표점)
    published_at       TEXT,               -- 게시/발표일(YYYY-MM-DD, 원문 표시일)
    source_name        TEXT,
    source_url         TEXT,
    source_tier        TEXT,               -- A|B|C|D
    source_type        TEXT,               -- official_current|official_retrospective|reported|reported_company_statement|third_party_estimate|target
    status             TEXT NOT NULL DEFAULT 'needs_review',
    confidence_score   REAL DEFAULT 0,
    evidence_text      TEXT,               -- 근거 문장(짧게)
    is_official        INTEGER DEFAULT 0,
    is_estimate        INTEGER DEFAULT 0,
    is_target          INTEGER DEFAULT 0,
    -- 계층형 검증(verified/corroborated/provisional/needs_review)
    verification_status TEXT DEFAULT 'needs_review',
    verification_reason TEXT,
    verified_at        TEXT,
    source_note        TEXT,   -- 원문 URL 없을 때 출처 설명(예: 사용자 제공 이미지 경로)
    evidence_note      TEXT,   -- 원문 evidence 미확보 시 근거 메모(원문 문장으로 저장 금지)
    source_locator     TEXT,   -- 기사 제목/식별자 등 위치 힌트
    -- 파생 observation(예: 월매출×12). 공식 ARR 로 표시하지 않음(is_official=0 강제).
    is_derived         INTEGER DEFAULT 0,
    calculation_method TEXT,               -- 예: monthly_revenue_x12
    derived_from_id    INTEGER,            -- 원본 observation runrate_updates.id
    supersedes_id      INTEGER,
    content_hash       TEXT UNIQUE,
    created_at         TEXT,
    updated_at         TEXT
);

-- 밸류에이션(펀딩 라운드)
CREATE TABLE IF NOT EXISTS valuation_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id         INTEGER REFERENCES companies(id),
    as_of_date         TEXT,               -- 기준일
    published_at       TEXT,               -- 발표일
    money_basis        TEXT,               -- pre_money | post_money
    valuation_usd_bn   REAL,
    investment_usd_bn  REAL,
    round_name         TEXT,               -- Series X 등
    source_name        TEXT,
    source_url         TEXT,
    is_official        INTEGER DEFAULT 0,
    evidence_text      TEXT,
    status             TEXT NOT NULL DEFAULT 'needs_review',
    content_hash       TEXT UNIQUE,
    created_at         TEXT,
    updated_at         TEXT
);

-- 제품별 지표(Claude Code 등)
CREATE TABLE IF NOT EXISTS product_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id         INTEGER REFERENCES companies(id),
    product            TEXT NOT NULL,       -- Claude Code 등
    metric_name        TEXT NOT NULL,       -- revenue_run_rate 등
    value_usd_bn       REAL,
    qualifier          TEXT DEFAULT 'exact',-- exact|over|approximately|range 등(원문 표현 보존)
    unit               TEXT,
    as_of_date         TEXT,
    date_precision     TEXT DEFAULT 'day',
    published_at       TEXT,
    source_name        TEXT,
    source_url         TEXT,
    is_official        INTEGER DEFAULT 0,
    status             TEXT NOT NULL DEFAULT 'needs_review',
    evidence_text      TEXT,
    content_hash       TEXT UNIQUE,
    created_at         TEXT,
    updated_at         TEXT
);

-- 차트 주석용 이벤트(모델 출시·가격변경·대형고객·파트너십·펀딩·클라우드계약 등)
CREATE TABLE IF NOT EXISTS source_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id         INTEGER REFERENCES companies(id),
    event_date         TEXT,
    event_type         TEXT,                -- model_release|pricing|customer|partnership|funding|cloud_deal
    title              TEXT,
    description        TEXT,
    source_url         TEXT,
    content_hash       TEXT UNIQUE,
    created_at         TEXT
);

-- 수집 실행 로그
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at         TEXT,
    finished_at        TEXT,
    mode               TEXT,                -- daily | discovery | backfill | health
    sources_searched   TEXT,                -- JSON 배열
    docs_found         INTEGER DEFAULT 0,
    new_candidates     INTEGER DEFAULT 0,
    confirmed          INTEGER DEFAULT 0,
    duplicates         INTEGER DEFAULT 0,
    skipped_cached     INTEGER DEFAULT 0,   -- ETag/Last-Modified/content_hash 동일 → 재분석 스킵
    api_calls          INTEGER DEFAULT 0,   -- LLM/외부 API 호출 수(비용 추적)
    est_tokens         INTEGER DEFAULT 0,   -- 추정 토큰 사용량
    errors             TEXT                 -- JSON/텍스트
);

-- 자동 추출했지만 확정 못한 후보(검토 대기)
CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id         INTEGER REFERENCES companies(id),
    runrate_update_id  INTEGER,             -- 연결된 runrate_updates.id (있으면)
    kind               TEXT DEFAULT 'runrate', -- runrate|valuation|product|event
    found_expression   TEXT,                -- 발견 원문 표현
    classification     TEXT,                -- 분류 추정
    source_name        TEXT,
    source_url         TEXT,
    source_tier        TEXT,
    confidence_score   REAL DEFAULT 0,
    evidence_text      TEXT,
    published_at       TEXT,
    as_of_start        TEXT,
    as_of_end          TEXT,
    payload_json       TEXT,                -- 승인 시 반영할 구조화 데이터
    content_hash       TEXT UNIQUE,
    status             TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected
    created_at         TEXT
);

-- discovery: sources.yml 에 없는 새 도메인 후보(자동 승격 금지)
CREATE TABLE IF NOT EXISTS source_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id             INTEGER REFERENCES companies(id),
    domain                 TEXT UNIQUE,
    source_name            TEXT,
    first_seen_at          TEXT,
    last_seen_at           TEXT,
    discovery_count        INTEGER DEFAULT 0,
    relevant_article_count INTEGER DEFAULT 0,
    direct_source_ratio    REAL DEFAULT 0,
    recommended_tier       TEXT,             -- 추천만(수동 승격 필요)
    confidence_score       REAL DEFAULT 0,
    status                 TEXT DEFAULT 'candidate'  -- candidate|promoted|ignored
);

-- 사용자 승인/수정/거절 피드백(재훈련 아님; 이후 분류에 참고)
CREATE TABLE IF NOT EXISTS classification_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id             INTEGER REFERENCES companies(id),
    candidate_id           INTEGER,
    source_domain          TEXT,
    original_classification TEXT,
    final_classification    TEXT,
    original_metric_scope   TEXT,
    final_metric_scope      TEXT,
    original_qualifier      TEXT,
    final_qualifier         TEXT,
    approval_action         TEXT,            -- approve|edit|reject
    correction_reason       TEXT,
    evidence_pattern        TEXT,            -- 근거 문장 특징(정규화)
    created_at              TEXT
);

-- 이상 탐지 큐(자동 삭제/수정 금지, 사람이 검토)
CREATE TABLE IF NOT EXISTS anomaly_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id             INTEGER REFERENCES companies(id),
    anomaly_type           TEXT,             -- stale_90d|estimate_gap|estimate_drop|accel|lower_official|date_inversion|same_date_conflict|qualifier_simplified|official_estimate_mix|requote_dup
    detail                 TEXT,
    related_id             INTEGER,
    detected_at            TEXT,
    status                 TEXT DEFAULT 'open'  -- open|reviewed|dismissed
);

-- HTTP 캐시(ETag/Last-Modified/content_hash 동일 시 재분석 스킵 → 토큰/비용 절감)
CREATE TABLE IF NOT EXISTS fetch_cache (
    url                    TEXT PRIMARY KEY,
    etag                   TEXT,
    last_modified          TEXT,
    content_hash           TEXT,
    last_fetched_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_rr_scope ON runrate_updates(metric_scope, metric_type, status);
CREATE INDEX IF NOT EXISTS idx_rr_official ON runrate_updates(is_official, as_of_end);
-- company_id 인덱스는 컬럼 ALTER 이후 db._migrate_companies 에서 생성(순서 의존).
CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);
CREATE INDEX IF NOT EXISTS idx_sc_status ON source_candidates(status);
CREATE INDEX IF NOT EXISTS idx_anom_status ON anomaly_queue(status);
"""
