# -*- coding: utf-8 -*-
"""seed 로더: 사전 검증된 구조화 데이터(CSV) 를 DB 에 병합.

seed 는 원문·근거문장이 확인된 것만. content_hash 로 재실행 중복 방지.
검증 안 된 숫자는 seed 에 넣지 않는다(needs_review 로 남기거나 아예 미입력).
"""
from __future__ import annotations
import csv
from pathlib import Path

from tracker import config, dedup
from tracker.database import db


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def load_runrate_seed(conn, path: Path) -> int:
    if not path.exists():
        return 0
    added = 0
    now = db.now_kst()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            low = _num(r.get("value_low_usd_bn"))
            high = _num(r.get("value_high_usd_bn"))
            qualifier = (r.get("qualifier") or "exact").strip()
            ch = r.get("content_hash") or dedup.content_hash(
                r.get("source_url", ""), r.get("source_name", ""),
                r.get("published_at"), low, high, qualifier, r.get("evidence_text", ""))
            row = {
                "company": r.get("company") or "Anthropic",
                "metric_scope": r.get("metric_scope") or config.SCOPE_COMPANY,
                "metric_type": r.get("metric_type") or config.METRIC_RUNRATE,
                "value_low_usd_bn": low, "value_high_usd_bn": high,
                "original_value": r.get("original_value"),
                "original_currency": r.get("original_currency") or "USD",
                "original_unit": r.get("original_unit"),
                "qualifier": qualifier,
                "as_of_start": r.get("as_of_start") or None,
                "as_of_end": r.get("as_of_end") or None,
                "date_precision": r.get("date_precision") or "day",
                "published_at": r.get("published_at") or None,
                "source_name": r.get("source_name"), "source_url": r.get("source_url"),
                "source_tier": r.get("source_tier"), "source_type": r.get("source_type"),
                "status": r.get("status") or config.STATUS_NEEDS_REVIEW,
                "confidence_score": _num(r.get("confidence_score")) or 0,
                "evidence_text": r.get("evidence_text"),
                "is_official": int(str(r.get("is_official", "0")).strip() in ("1", "true", "True")),
                "is_estimate": int(str(r.get("is_estimate", "0")).strip() in ("1", "true", "True")),
                "is_target": int(str(r.get("is_target", "0")).strip() in ("1", "true", "True")),
                "content_hash": ch, "created_at": now, "updated_at": now,
            }
            if db.insert(conn, "runrate_updates", row) is not None:
                added += 1
    return added


def load_valuation_seed(conn, path: Path) -> int:
    if not path.exists():
        return 0
    added = 0
    now = db.now_kst()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            val = _num(r.get("valuation_usd_bn"))
            ch = r.get("content_hash") or dedup.content_hash(
                r.get("source_url", ""), r.get("round_name", ""),
                r.get("published_at"), val, None, r.get("money_basis", ""))
            row = {
                "as_of_date": r.get("as_of_date") or None, "published_at": r.get("published_at") or None,
                "money_basis": r.get("money_basis"), "valuation_usd_bn": val,
                "investment_usd_bn": _num(r.get("investment_usd_bn")),
                "round_name": r.get("round_name"), "source_name": r.get("source_name"),
                "source_url": r.get("source_url"),
                "is_official": int(str(r.get("is_official", "0")).strip() in ("1", "true", "True")),
                "evidence_text": r.get("evidence_text"),
                "status": r.get("status") or config.STATUS_NEEDS_REVIEW,
                "content_hash": ch, "created_at": now, "updated_at": now,
            }
            if db.insert(conn, "valuation_updates", row) is not None:
                added += 1
    return added


def load_product_seed(conn, path: Path) -> int:
    if not path.exists():
        return 0
    added = 0
    now = db.now_kst()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            val = _num(r.get("value_usd_bn"))
            ch = r.get("content_hash") or dedup.content_hash(
                r.get("source_url", ""), r.get("product", ""), r.get("published_at"),
                val, None, r.get("metric_name", ""))
            row = {
                "product": r.get("product"), "metric_name": r.get("metric_name"),
                "value_usd_bn": val, "qualifier": r.get("qualifier") or "exact",
                "unit": r.get("unit"), "date_precision": r.get("date_precision") or "day",
                "as_of_date": r.get("as_of_date") or None, "published_at": r.get("published_at") or None,
                "source_name": r.get("source_name"), "source_url": r.get("source_url"),
                "is_official": int(str(r.get("is_official", "0")).strip() in ("1", "true", "True")),
                "status": r.get("status") or config.STATUS_NEEDS_REVIEW,
                "evidence_text": r.get("evidence_text"),
                "content_hash": ch, "created_at": now, "updated_at": now,
            }
            if db.insert(conn, "product_metrics", row) is not None:
                added += 1
    return added


def load_events_seed(conn, path: Path) -> int:
    if not path.exists():
        return 0
    added = 0
    now = db.now_kst()
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ch = r.get("content_hash") or dedup.content_hash(
                r.get("source_url", ""), r.get("title", ""), r.get("event_date"),
                None, None, r.get("event_type", ""))
            row = {
                "event_date": r.get("event_date") or None, "event_type": r.get("event_type"),
                "title": r.get("title"), "description": r.get("description"),
                "source_url": r.get("source_url"), "content_hash": ch, "created_at": now,
            }
            if db.insert(conn, "source_events", row) is not None:
                added += 1
    return added


def load_all_seeds(conn, seeds_dir: Path | None = None) -> dict:
    d = seeds_dir or config.SEEDS_DIR
    return {
        "runrate": load_runrate_seed(conn, d / "runrate_updates.csv"),
        "valuation": load_valuation_seed(conn, d / "valuation_updates.csv"),
        "product": load_product_seed(conn, d / "product_metrics.csv"),
        "events": load_events_seed(conn, d / "events.csv"),
    }
