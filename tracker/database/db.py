# -*- coding: utf-8 -*-
"""SQLite 연결·초기화·공용 CRUD 헬퍼."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Iterable

from tracker import config
from tracker.database.schema import DDL, SCHEMA_VERSION

_KST = ZoneInfo(config.TZ)


def now_kst() -> str:
    return datetime.now(timezone.utc).astimezone(_KST).strftime("%Y-%m-%d %H:%M:%S")


def connect(path: str | None = None) -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(path or str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# 스키마 진화: 기존 DB 에 누락된 컬럼을 멱등적으로 추가(CREATE TABLE IF NOT EXISTS 는 컬럼 추가 안 함).
_CID = ("company_id", "INTEGER")   # 다중 회사 FK(→ companies.id)
_MIGRATIONS = {
    "runrate_updates": [("date_precision", "TEXT DEFAULT 'day'"),
                        ("display_date", "TEXT"),
                        ("verification_status", "TEXT DEFAULT 'needs_review'"),
                        ("verification_reason", "TEXT"), ("verified_at", "TEXT"),
                        ("source_note", "TEXT"), ("evidence_note", "TEXT"),
                        ("source_locator", "TEXT"), _CID,
                        ("is_derived", "INTEGER DEFAULT 0"),
                        ("calculation_method", "TEXT"), ("derived_from_id", "INTEGER")],
    "valuation_updates": [_CID],
    "product_metrics": [("qualifier", "TEXT DEFAULT 'exact'"),
                        ("date_precision", "TEXT DEFAULT 'day'"), _CID],
    "source_events": [_CID],
    "review_queue": [_CID],
    "source_candidates": [_CID],
    "anomaly_queue": [_CID, ("dismiss_reason", "TEXT"), ("dismissed_at", "TEXT"),
                      ("audit_json", "TEXT"), ("superseded_by", "INTEGER"),
                      ("anomaly_key", "TEXT"), ("last_seen_at", "TEXT"),
                      ("age_days", "INTEGER"), ("occurrence_count", "INTEGER DEFAULT 1")],
    "classification_feedback": [_CID],
    "ingestion_runs": [("mode", "TEXT"), ("skipped_cached", "INTEGER DEFAULT 0"),
                       ("api_calls", "INTEGER DEFAULT 0"), ("est_tokens", "INTEGER DEFAULT 0")],
}

# 초기 회사(슬러그, 표시명, 공식 도메인). migration 시 없으면 seed.
_SEED_COMPANIES = [
    ("anthropic", "Anthropic", "anthropic.com"),
    ("openai", "OpenAI", "openai.com"),
]
# content_hash 를 보유해 회사 스코프 래핑 대상이 되는 테이블
_HASH_TABLES = ("runrate_updates", "valuation_updates", "product_metrics",
                "source_events", "review_queue")
# company_id 를 backfill 할 테이블(기존 레코드 → anthropic)
_COMPANY_TABLES = ("runrate_updates", "valuation_updates", "product_metrics",
                   "source_events", "review_queue", "source_candidates",
                   "anomaly_queue", "classification_feedback")


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    r = conn.execute("SELECT value FROM schema_meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO schema_meta(key,value) VALUES(?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def company_id_by_slug(conn: sqlite3.Connection, slug: str) -> int | None:
    r = conn.execute("SELECT id FROM companies WHERE slug=?", (slug,)).fetchone()
    return r[0] if r else None


def ensure_company(conn: sqlite3.Connection, slug: str, display_name: str,
                   official_domain: str | None = None) -> int:
    cid = company_id_by_slug(conn, slug)
    if cid is not None:
        return cid
    conn.execute("INSERT INTO companies(slug, display_name, official_domain, created_at) "
                 "VALUES(?,?,?,?)", (slug, display_name, official_domain, now_kst()))
    conn.commit()
    return company_id_by_slug(conn, slug)


def _migrate_companies(conn: sqlite3.Connection) -> None:
    """다중 회사 migration(멱등): 회사 seed → 기존 레코드 company_id=anthropic →
    content_hash 회사 스코프 래핑(1회). 기존 데이터 삭제 없음."""
    from tracker import dedup
    # 1) 초기 회사 seed
    for slug, name, domain in _SEED_COMPANIES:
        ensure_company(conn, slug, name, domain)
    anth = company_id_by_slug(conn, "anthropic")
    # 2) 기존 레코드 → anthropic (company_id NULL 인 것만)
    #    anomaly_queue 는 제외 — 탐지 결과는 회사가 detail 로 판별되며, 일괄 anthropic 지정은 오라벨이 된다.
    #    (탐지 시점에 company_id 를 직접 기록한다 → health.detect_anomalies)
    for table in _COMPANY_TABLES:
        if table == "anomaly_queue":
            continue
        if "company_id" in _columns(conn, table):
            conn.execute(f"UPDATE {table} SET company_id=? WHERE company_id IS NULL", (anth,))
    # 3) content_hash 회사 스코프 래핑 — 1회만(플래그로 재실행 방지)
    if _meta(conn, "hash_scoped") != "v5":
        for table in _HASH_TABLES:
            cols = _columns(conn, table)
            if "content_hash" not in cols or "company_id" not in cols:
                continue
            rows = conn.execute(
                f"SELECT t.id, t.content_hash, c.slug FROM {table} t "
                "LEFT JOIN companies c ON c.id=t.company_id "
                "WHERE t.content_hash IS NOT NULL").fetchall()
            for rid, ch, slug in rows:
                conn.execute(f"UPDATE {table} SET content_hash=? WHERE id=?",
                             (dedup.scoped_hash(slug or "anthropic", ch), rid))
        _set_meta(conn, "hash_scoped", "v5")
    # 4) company_id 인덱스(컬럼 ALTER 이후 생성)
    for stmt in (
        "CREATE INDEX IF NOT EXISTS idx_rr_company ON runrate_updates(company_id, metric_scope, status)",
        "CREATE INDEX IF NOT EXISTS idx_val_company ON valuation_updates(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_prod_company ON product_metrics(company_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_evt_company ON source_events(company_id)",
    ):
        conn.execute(stmt)
    conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    for table, cols in _MIGRATIONS.items():
        existing = _columns(conn, table)
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    # 컬럼 ALTER 이후에만 만들 수 있는 인덱스
    conn.execute("CREATE INDEX IF NOT EXISTS idx_anom_key ON anomaly_queue(anomaly_key)")
    conn.commit()
    _migrate_companies(conn)


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    migrate(conn)
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def insert(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> int | None:
    """content_hash 중복이면 무시(None 반환). 신규면 rowid 반환."""
    cols = ", ".join(row.keys())
    ph = ", ".join(["?"] * len(row))
    try:
        cur = conn.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({ph})", list(row.values())
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # UNIQUE(content_hash) 충돌 = 중복


def exists_hash(conn: sqlite3.Connection, table: str, content_hash: str) -> bool:
    cur = conn.execute(f"SELECT 1 FROM {table} WHERE content_hash=? LIMIT 1", (content_hash,))
    return cur.fetchone() is not None


def fetchall(conn: sqlite3.Connection, sql: str, args: Iterable = ()) -> list[sqlite3.Row]:
    return conn.execute(sql, tuple(args)).fetchall()


def fetchone(conn: sqlite3.Connection, sql: str, args: Iterable = ()) -> sqlite3.Row | None:
    return conn.execute(sql, tuple(args)).fetchone()
