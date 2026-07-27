# -*- coding: utf-8 -*-
"""SQLite → 정적 dashboard.json 생성(비밀 없음). 프론트가 이 JSON만 소비.

공식/추정/목표 시계열을 분리해 담는다(한 선으로 연결 금지는 프론트에서 처리).
확정(confirmed) 데이터만 시계열에 넣고, needs_review 는 품질 카운트로만 반영.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tracker import config
from tracker.database import db
from tracker.metrics import calc

_KST = ZoneInfo(config.TZ)


def _rows(conn, sql, args=()):
    return [dict(r) for r in db.fetchall(conn, sql, args)]


def _point(r: dict) -> dict:
    return {
        "value_low_usd_bn": r.get("value_low_usd_bn"),
        "value_high_usd_bn": r.get("value_high_usd_bn"),
        "qualifier": r.get("qualifier"),
        "as_of_start": r.get("as_of_start"), "as_of_end": r.get("as_of_end"),
        "date_precision": r.get("date_precision"),
        "published_at": r.get("published_at"),
        "source_name": r.get("source_name"), "source_url": r.get("source_url"),
        "source_tier": r.get("source_tier"), "source_type": r.get("source_type"),
        "confidence_score": r.get("confidence_score"),
        "evidence_text": r.get("evidence_text"),
        "is_official": r.get("is_official"), "is_estimate": r.get("is_estimate"),
        "is_target": r.get("is_target"),
    }


def build_payload(conn) -> dict:
    confirmed = _rows(
        conn,
        "SELECT * FROM runrate_updates WHERE status=? AND metric_scope=? "
        "ORDER BY as_of_end ASC",
        (config.STATUS_CONFIRMED, config.SCOPE_COMPANY),
    )
    official = [_point(r) for r in confirmed if r.get("is_official")]
    estimated = [_point(r) for r in confirmed if r.get("is_estimate")]
    targets = [_point(r) for r in confirmed if r.get("is_target")]
    reported = [_point(r) for r in confirmed
                if not r.get("is_official") and not r.get("is_estimate") and not r.get("is_target")]

    valuations = _rows(conn, "SELECT * FROM valuation_updates WHERE status=? ORDER BY as_of_date ASC",
                       (config.STATUS_CONFIRMED,))
    products = _rows(conn, "SELECT * FROM product_metrics WHERE status=? ORDER BY as_of_date ASC",
                     (config.STATUS_CONFIRMED,))
    events = _rows(conn, "SELECT * FROM source_events ORDER BY event_date ASC")

    all_points = official + estimated + targets
    metrics = {
        "latest_official": calc.latest_official(all_points),
        "latest_estimate": calc.latest_estimate(all_points),
        "official_estimate_gap": calc.official_estimate_gap(all_points),
        "growth_velocity": calc.growth_velocity(all_points),
        "acceleration": calc.acceleration(all_points),
        "target_progress": calc.target_progress(all_points),
        "valuation_multiple": calc.valuation_multiple(all_points, valuations),
        "product_contribution": calc.product_contribution(all_points, products),
    }

    # 데이터 품질
    def _count(sql, args=()):
        r = db.fetchone(conn, sql, args)
        return r[0] if r else 0

    last_run = db.fetchone(conn, "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1")
    quality = {
        "official_count": len(official),
        "estimate_count": len(estimated),
        "target_count": len(targets),
        "review_queue_count": _count("SELECT COUNT(*) FROM review_queue WHERE status='pending'"),
        "uncertain_asof_count": _count(
            "SELECT COUNT(*) FROM runrate_updates WHERE status=? AND "
            "(as_of_end IS NULL OR (as_of_start IS NOT NULL AND as_of_start <> as_of_end))",
            (config.STATUS_CONFIRMED,)),
        "last_collect": (dict(last_run).get("finished_at") if last_run else None),
        "last_errors": (json.loads(dict(last_run).get("errors") or "[]") if last_run else []),
    }

    freshness = {
        "latest_official_as_of": (official[-1]["as_of_end"] if official else None),
        "generated_kst": datetime.now(timezone.utc).astimezone(_KST).strftime("%Y-%m-%d %H:%M"),
    }

    return {
        "display_name": "Anthropic Revenue Run-rate Tracker",
        "note": "Revenue Run-rate 는 회계상 연간 매출과 다릅니다. 공식/추정 시계열은 분리 표시됩니다.",
        "series": {"official": official, "estimated": estimated, "reported": reported,
                   "target": targets},
        "valuations": valuations, "products": products, "events": events,
        "metrics": metrics, "quality": quality, "freshness": freshness,
    }


def write_dashboard(conn, path=None) -> str:
    payload = build_payload(conn)
    out = path or config.DASHBOARD_JSON
    config.ensure_dirs()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)
