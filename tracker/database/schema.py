# -*- coding: utf-8 -*-
"""SQLite 스키마 정의 + 간단 migration.

설계 원칙:
· 공식/추정/목표를 is_official/is_estimate/is_target 로 분리(같은 시계열로 섞지 않음).
· 숫자표현: value_low/high_usd_bn + qualifier 로 '$30B 이상' 등을 정확값처럼 저장하지 않음.
· 날짜: published_at(게시일) 과 as_of_start/end(기준시점) 분리.
· 중복: content_hash 로 동일 발표 재인용을 새 포인트로 추가하지 않음.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY, value TEXT
);

-- 핵심: run-rate/매출 업데이트 (공식·보도·추정·목표 모두 여기, 플래그로 구분)
CREATE TABLE IF NOT EXISTS runrate_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company            TEXT NOT NULL DEFAULT 'Anthropic',
    metric_scope       TEXT NOT NULL,      -- company | product
    metric_type        TEXT NOT NULL,      -- revenue_run_rate 등
    value_low_usd_bn   REAL,               -- USD billion 표준(하단)
    value_high_usd_bn  REAL,               -- 범위 상단(단일값이면 NULL)
    original_value     TEXT,               -- 원문 숫자 문자열(보존)
    original_currency  TEXT DEFAULT 'USD',
    original_unit      TEXT,               -- million | billion 등 원문 단위
    qualifier          TEXT NOT NULL,      -- exact|approximately|over|range|target|estimate|reported
    as_of_start        TEXT,               -- 기준시점 시작(YYYY-MM-DD)
    as_of_end          TEXT,               -- 기준시점 끝(불명확 시 월범위)
    date_precision     TEXT DEFAULT 'day', -- day | month_range | quarter | unknown (기준일 정밀도)
    published_at       TEXT,               -- 게시/발표일(YYYY-MM-DD, 원문 표시일)
    source_name        TEXT,
    source_url         TEXT,
    source_tier        TEXT,               -- A|B|C|D
    source_type        TEXT,               -- official|reported|estimate|target|social 등
    status             TEXT NOT NULL DEFAULT 'needs_review',
    confidence_score   REAL DEFAULT 0,
    evidence_text      TEXT,               -- 근거 문장(짧게)
    is_official        INTEGER DEFAULT 0,
    is_estimate        INTEGER DEFAULT 0,
    is_target          INTEGER DEFAULT 0,
    supersedes_id      INTEGER,
    content_hash       TEXT UNIQUE,
    created_at         TEXT,
    updated_at         TEXT
);

-- 밸류에이션(펀딩 라운드)
CREATE TABLE IF NOT EXISTS valuation_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    sources_searched   TEXT,                -- JSON 배열
    docs_found         INTEGER DEFAULT 0,
    new_candidates     INTEGER DEFAULT 0,
    confirmed          INTEGER DEFAULT 0,
    duplicates         INTEGER DEFAULT 0,
    errors             TEXT                 -- JSON/텍스트
);

-- 자동 추출했지만 확정 못한 후보(검토 대기)
CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE INDEX IF NOT EXISTS idx_rr_scope ON runrate_updates(metric_scope, metric_type, status);
CREATE INDEX IF NOT EXISTS idx_rr_official ON runrate_updates(is_official, as_of_end);
CREATE INDEX IF NOT EXISTS idx_rq_status ON review_queue(status);
"""
