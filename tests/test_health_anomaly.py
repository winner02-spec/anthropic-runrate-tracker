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


def _official(conn, cid, company, value, as_of, metric_type=config.MT_ARR):
    now = db.now_kst()
    db.insert(conn, "runrate_updates", {
        "company": company, "company_id": cid, "metric_scope": config.SCOPE_COMPANY,
        "metric_type": metric_type, "value_low_usd_bn": value, "value_high_usd_bn": None,
        "qualifier": "exact", "as_of_start": as_of, "as_of_end": as_of, "published_at": as_of,
        "date_precision": "day", "source_name": f"{company} (공식)", "source_type": "official_current",
        "source_tier": "A", "is_official": 1, "is_estimate": 0, "is_target": 0,
        "verification_status": config.VS_CORROBORATED, "status": config.STATUS_CONFIRMED,
        "content_hash": f"off-{company}-{value}-{as_of}", "created_at": now, "updated_at": now})


def test_recompute_twice_creates_no_duplicate_rows(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    _official(conn, cid, "OpenAI", 20.0, "2025-12-31")          # 90일 이상 경과 → stale_90d
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")   # 공식대비 +20%↑ → estimate_gap

    first = health.record_anomalies(conn, health.detect_anomalies(conn, record=False))
    n1 = db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue")[0]
    second = health.record_anomalies(conn, health.detect_anomalies(conn, record=False))
    n2 = db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue")[0]

    assert first["inserted"] > 0
    assert second["inserted"] == 0          # 2회차 신규 중복 0
    assert second["updated"] == first["detected"]
    assert n1 == n2                          # 새 행이 생기지 않는다
    # 상태 지속형 경고는 새 행 대신 갱신(last_seen_at·age_days·occurrence_count)
    stale = dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE anomaly_type='stale_90d'"))
    assert stale["age_days"] and stale["age_days"] >= 90
    assert stale["last_seen_at"] and stale["occurrence_count"] == 2
    assert stale["anomaly_key"].startswith(f"{cid}|stale_90d|")


def test_ownership_resolved_from_linked_observations(tmp_path):
    conn = _conn(tmp_path)
    oai = db.company_id_by_slug(conn, "openai")
    anth = db.company_id_by_slug(conn, "anthropic")
    _official(conn, oai, "OpenAI", 20.0, "2025-12-31")
    _est(conn, oai, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _official(conn, anth, "Anthropic", 47.0, "2026-05-15", metric_type=config.MT_RUNRATE)

    # 레거시 일괄 backfill 로 company_id 가 anthropic 으로 잘못 채워진 OpenAI anomaly
    conn.execute("INSERT INTO anomaly_queue(company_id, anomaly_type, detail, detected_at, status) "
                 "VALUES(?,?,?,?, 'open')",
                 (anth, "estimate_gap", "[openai] 추정 42.6 > 공식 20.0 +20%↑", db.now_kst()))
    conn.commit()
    aid = db.fetchone(conn, "SELECT id FROM anomaly_queue")[0]

    res = health.correct_anomaly_ownership(conn, ids=[aid])[0]
    assert res["action"] == "corrected" and res["to"] == oai
    # detail 문자열이 아니라 연결 observation(공식·추정 id)으로 확인했는지
    assert res["evidence"]["official_observation_id"] and res["evidence"]["estimate_observation_id"]

    row = dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (aid,)))
    assert row["company_id"] == oai
    audit = json.loads(row["audit_json"])
    assert audit["original_company_id"] == anth
    assert audit["corrected_company_id"] == oai
    assert audit["correction_reason"] == "legacy_migration_company_mismatch"
    assert audit["corrected_at"]


def test_supersede_keeps_audit_and_is_not_reopened(tmp_path):
    conn = _conn(tmp_path)
    cid = db.company_id_by_slug(conn, "openai")
    _official(conn, cid, "OpenAI", 20.0, "2025-12-31")
    _est(conn, cid, 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    health.detect_anomalies(conn, record=True)
    gap = dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE anomaly_type='estimate_gap'"))

    # 중복으로 쌓였다고 가정한 옛 행(key 없음) → superseded
    conn.execute("INSERT INTO anomaly_queue(company_id, anomaly_type, detail, detected_at, status) "
                 "VALUES(?,?,?,?, 'open')",
                 (cid, "estimate_gap", "[openai] 추정 42.6 > 공식 20.0 +20%↑", db.now_kst()))
    conn.commit()
    old_id = db.fetchone(conn, "SELECT id FROM anomaly_queue ORDER BY id DESC LIMIT 1")[0]

    res = health.supersede_anomaly(conn, old_id, gap["id"])
    assert res["status"] == "superseded" and res["superseded_by"] == gap["id"]
    assert res["dismiss_reason"] == "duplicate_recompute"
    audit = json.loads(res["audit_json"])
    assert audit["original_detail"] and audit["original_status"] == "open"

    # 재계산해도 superseded 를 되살리지 않는다
    health.detect_anomalies(conn, record=True)
    assert dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (old_id,)))["status"] == "superseded"


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
