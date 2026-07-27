# -*- coding: utf-8 -*-
"""health check + 이상 탐지(item 13). 이상은 자동 삭제/수정하지 않고 anomaly_queue 에 남긴다.
외부 기사 본문 재분석은 하지 않는다(비용 0)."""
from __future__ import annotations
import json
from datetime import date

from tracker import config
from tracker.database import db
from tracker.metrics import calc
from tracker import verify


def _points(conn):
    return [dict(r) for r in db.fetchall(
        conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,))]


def detect_anomalies(conn, record: bool = True) -> list[dict]:
    pts = _points(conn)
    anomalies: list[dict] = []

    def add(typ, detail):
        anomalies.append({"type": typ, "detail": detail})

    off = calc.latest_official(pts)
    est = calc.latest_estimate(pts)

    # 90일 이상 공식 업데이트 없음
    if off and off.get("as_of_end"):
        try:
            lag = (date.today() - date.fromisoformat(off["as_of_end"])).days
            if lag >= 90:
                add("stale_90d", f"최신 공식 {off['as_of_end']} ({lag}일 경과)")
        except ValueError:
            pass
    # 외부추정이 마지막 공식보다 20%+ 높음
    if off and est and off.get("value_low_usd_bn") and est.get("value_low_usd_bn"):
        if est["value_low_usd_bn"] > off["value_low_usd_bn"] * 1.2:
            add("estimate_gap", f"추정 {est['value_low_usd_bn']} > 공식 {off['value_low_usd_bn']} +20%↑")
    # 외부추정 감소 / 공식 하락
    def series(pred):
        xs = [p for p in pts if pred(p) and p.get("as_of_end") and p.get("value_low_usd_bn") is not None]
        return sorted(xs, key=lambda p: p["as_of_end"])
    est_s = series(lambda p: p.get("is_estimate"))
    if len(est_s) >= 2 and est_s[-1]["value_low_usd_bn"] < est_s[-2]["value_low_usd_bn"]:
        add("estimate_drop", f"{est_s[-2]['as_of_end']} {est_s[-2]['value_low_usd_bn']} → {est_s[-1]['as_of_end']} {est_s[-1]['value_low_usd_bn']}")
    off_s = series(lambda p: p.get("is_official"))
    if len(off_s) >= 2 and off_s[-1]["value_low_usd_bn"] < off_s[-2]["value_low_usd_bn"]:
        add("lower_official", f"{off_s[-2]['value_low_usd_bn']} → {off_s[-1]['value_low_usd_bn']}")
    # 급가속/감속
    acc = calc.acceleration(pts)
    if acc.get("state") in ("accelerating", "decelerating"):
        add("accel", f"{acc['state']} (recent {acc.get('recent_per30')} / prior {acc.get('prior_per30')})")

    # verify-history 항목(날짜역전·같은날상충·혼입·qualifier손실·재인용중복)
    vh = verify.verify_history(conn)
    for typ in ("date_inversions", "same_date_conflicts", "official_estimate_mix",
                "qualifier_loss", "requote_duplicates"):
        for it in vh["issues"].get(typ, []):
            add(typ, it)

    if record and anomalies:
        now = db.now_kst()
        for a in anomalies:
            # 동일 미해결 이상 중복 적재 방지
            exists = db.fetchone(conn, "SELECT 1 FROM anomaly_queue WHERE anomaly_type=? AND detail=? "
                                       "AND status='open' LIMIT 1", (a["type"], a["detail"]))
            if not exists:
                conn.execute("INSERT INTO anomaly_queue(anomaly_type, detail, detected_at, status) "
                             "VALUES(?,?,?, 'open')", (a["type"], a["detail"], now))
        conn.commit()
    return anomalies


def run_health(conn) -> dict:
    last = db.fetchone(conn, "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1")
    last_d = dict(last) if last else {}
    errs = []
    try:
        errs = json.loads(last_d.get("errors") or "[]")
    except Exception:
        errs = []
    review_pending = db.fetchone(conn, "SELECT COUNT(*) FROM review_queue WHERE status='pending'")[0]
    anomalies = detect_anomalies(conn, record=True)
    anom_open = db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue WHERE status='open'")[0]
    export_ready = config.DASHBOARD_JSON.exists()
    fp = db.fetchone(conn, "SELECT value FROM schema_meta WHERE key='data_fp'")
    return {
        "last_collect": last_d.get("finished_at"),
        "last_mode": last_d.get("mode"),
        "parser_errors": errs[:5],
        "review_queue_pending": review_pending,
        "anomalies_new": len(anomalies),
        "anomaly_queue_open": anom_open,
        "export_ready": export_ready,
        "deploy_fingerprint": fp["value"] if fp else None,
    }
