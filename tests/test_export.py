# -*- coding: utf-8 -*-
import json
from tracker import config
from tracker.database import db
from tracker.export import dashboard


def _seed_conn(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    now = db.now_kst()
    base = {"company": "Anthropic", "metric_scope": config.SCOPE_COMPANY,
            "metric_type": config.METRIC_RUNRATE, "value_high_usd_bn": None,
            "original_currency": "USD", "original_unit": "billion",
            "source_url": "https://www.anthropic.com/news/x", "evidence_text": "ev",
            "verification_status": config.VS_VERIFIED,
            "status": config.STATUS_CONFIRMED, "created_at": now, "updated_at": now}
    db.insert(conn, "runrate_updates", {**base, "value_low_usd_bn": 14, "qualifier": "exact",
              "as_of_start": "2026-02-12", "as_of_end": "2026-02-12", "published_at": "2026-02-12",
              "source_tier": "A", "source_type": "official", "is_official": 1, "is_estimate": 0,
              "is_target": 0, "content_hash": "h1", "confidence_score": 0.9})
    db.insert(conn, "runrate_updates", {**base, "value_low_usd_bn": 20, "qualifier": "estimate",
              "as_of_start": "2026-03-01", "as_of_end": "2026-03-01", "published_at": "2026-03-01",
              "source_tier": "C", "source_type": "estimate", "is_official": 0, "is_estimate": 1,
              "is_target": 0, "content_hash": "h2", "confidence_score": 0.4})
    return conn


def test_export_separates_official_and_estimate(tmp_path):
    conn = _seed_conn(tmp_path)
    payload = dashboard.build_payload(conn)
    assert len(payload["series"]["official"]) == 1
    assert len(payload["series"]["estimated"]) == 1
    # 공식/추정 분리 — 같은 리스트에 섞이지 않음
    assert payload["series"]["official"][0]["value_low_usd_bn"] == 14
    assert payload["series"]["estimated"][0]["value_low_usd_bn"] == 20
    assert "metrics" in payload and "quality" in payload
    assert payload["quality"]["official_count"] == 1


def test_provenance_validation_blocks_export(tmp_path):
    import pytest
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    now = db.now_kst()
    # source_url·evidence 없는 확정 관측치 → export 실패해야 함(item 6)
    db.insert(conn, "runrate_updates", {
        "company": "Anthropic", "metric_scope": config.SCOPE_COMPANY,
        "metric_type": config.METRIC_RUNRATE, "value_low_usd_bn": 14, "qualifier": "exact",
        "as_of_end": "2026-02-12", "published_at": "2026-02-12",  # source_url/evidence 누락
        "verification_status": config.VS_VERIFIED,   # verified 인데 필수필드 누락 → 실패해야
        "source_type": "official_current", "is_official": 1, "status": config.STATUS_CONFIRMED,
        "content_hash": "hx", "created_at": now, "updated_at": now})
    with pytest.raises(dashboard.ProvenanceError):
        dashboard.write_dashboard(conn, tmp_path / "d.json")


def test_export_writes_valid_json(tmp_path):
    conn = _seed_conn(tmp_path)
    out = tmp_path / "dashboard.json"
    dashboard.write_dashboard(conn, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["display_name"].startswith("Anthropic")
