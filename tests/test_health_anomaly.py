# -*- coding: utf-8 -*-
"""이상 탐지: 외부추정 하락은 같은 시계열(회사·metric_type·기관·기준일 명확) 안에서만 판정한다.
기관간 값 차이는 '하락' 이 아니라 estimate_dispersion(안내)."""
import json

from tracker import config, health
from tracker.database import db


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "h.sqlite"))
    db.init_db(conn)
    return conn


def _est(conn, cid, value, as_of, source_name, date_precision="day", metric_type=config.MT_ARR):
    now = db.now_kst()
    db.insert(conn, "runrate_updates", {
        "company": "OpenAI", "company_id": cid, "metric_scope": config.SCOPE_COMPANY,
        "metric_type": metric_type, "value_low_usd_bn": value, "value_high_usd_bn": None,
        "qualifier": "estimate", "as_of_start": as_of, "as_of_end": as_of, "published_at": as_of,
        "date_precision": date_precision,
        "source_name": source_name, "source_type": "third_party_estimate", "source_tier": "C",
        "is_official": 0, "is_estimate": 1, "is_target": 0,
        "verification_status": config.VS_PROVISIONAL, "status": config.STATUS_CONFIRMED,
        "content_hash": f"{source_name}-{metric_type}-{value}-{as_of}", "created_at": now,
        "updated_at": now})


def test_estimate_drop_not_flagged_across_sources(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    # Funda $49B(7/28) → TickerTrends $42.6B(7/29): 기관이 다르므로 하락 아님
    _est(conn, cid, 33.0, "2026-05-30", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 49.0, "2026-07-28", "Funda (Axios 재인용, 원자료 미확인)")
    drops = [a for a in health.detect_anomalies(conn, record=False) if a["type"] == "estimate_drop"]
    assert drops == []


def test_estimate_drop_flagged_within_same_source(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 40.0, "2026-07-31", "TickerTrends (OpenAI ARR 추정)")
    drops = [a for a in health.detect_anomalies(conn, record=False) if a["type"] == "estimate_drop"]
    assert len(drops) == 1
    assert "TickerTrends" in drops[0]["detail"]
    assert drops[0]["company_id"] == cid          # 회사 라벨을 탐지 시점에 기록


def test_estimate_drop_ignores_other_metric_type_and_unclear_date(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    # 같은 기관이라도 metric_type 이 다르면 같은 시계열이 아니다
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 3.5, "2026-07-31", "TickerTrends (OpenAI ARR 추정)",
         metric_type=config.MT_RUNRATE)
    # 기준일이 불명확한 후보(date_precision=unknown)는 하락 계산에서 제외
    _est(conn, cid, 30.0, "2026-07-30", "TickerTrends (OpenAI ARR 추정)", date_precision="unknown")
    drops = [a for a in health.detect_anomalies(conn, record=False) if a["type"] == "estimate_drop"]
    assert drops == []


def test_cross_source_gap_reported_as_dispersion_not_error(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 25.0, "2026-02-28", "Sacra (OpenAI 매출 추정)")
    types = [a["type"] for a in health.detect_anomalies(conn, record=False)]
    assert "estimate_drop" not in types
    disp = [a for a in health.detect_anomalies(conn, record=False) if a["type"] == "estimate_dispersion"]
    assert len(disp) == 1
    assert "TickerTrends" in disp[0]["detail"] and "Sacra" in disp[0]["detail"]
    assert "오류 아님" in disp[0]["detail"]


def test_dismiss_preserves_audit_and_is_not_regenerated(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, cid, 40.0, "2026-07-31", "TickerTrends (OpenAI ARR 추정)")
    health.detect_anomalies(conn, record=True)
    row = dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE anomaly_type='estimate_drop'"))

    res = health.dismiss_anomaly(conn, row["id"], "cross_source_not_comparable")
    assert res["status"] == "dismissed"
    assert res["dismiss_reason"] == "cross_source_not_comparable" and res["dismissed_at"]
    audit = json.loads(res["audit_json"])
    assert audit["original_detail"] == row["detail"]      # 원 탐지값 보존(삭제·수정 아님)
    assert audit["original_status"] == "open"

    # 재계산해도 dismissed 건을 다시 open 으로 만들지 않는다
    health.detect_anomalies(conn, record=True)
    same = db.fetchall(conn, "SELECT status FROM anomaly_queue WHERE anomaly_type='estimate_drop'")
    assert [r["status"] for r in same] == ["dismissed"]
