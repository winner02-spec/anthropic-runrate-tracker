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
_MIGRATIONS = {
    "runrate_updates": [("date_precision", "TEXT DEFAULT 'day'"),
                        ("display_date", "TEXT"),
                        ("verification_status", "TEXT DEFAULT 'needs_review'"),
                        ("verification_reason", "TEXT"), ("verified_at", "TEXT"),
                        ("source_note", "TEXT"), ("evidence_note", "TEXT"),
                        ("source_locator", "TEXT")],
    "product_metrics": [("qualifier", "TEXT DEFAULT 'exact'"),
                        ("date_precision", "TEXT DEFAULT 'day'")],
    "ingestion_runs": [("mode", "TEXT"), ("skipped_cached", "INTEGER DEFAULT 0"),
                       ("api_calls", "INTEGER DEFAULT 0"), ("est_tokens", "INTEGER DEFAULT 0")],
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def migrate(conn: sqlite3.Connection) -> None:
    for table, cols in _MIGRATIONS.items():
        existing = _columns(conn, table)
        for name, decl in cols:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
    conn.commit()


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
