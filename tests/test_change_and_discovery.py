# -*- coding: utf-8 -*-
from tracker.database import db
from tracker import config, ingest
from tracker.export import dashboard


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    return conn


def _add_official(conn, v, d, ch):
    now = db.now_kst()
    db.insert(conn, "runrate_updates", {
        "company": "Anthropic", "metric_scope": config.SCOPE_COMPANY,
        "metric_type": config.METRIC_RUNRATE, "value_low_usd_bn": v, "qualifier": "exact",
        "as_of_start": d, "as_of_end": d, "date_precision": "day", "published_at": d,
        "source_url": "https://www.anthropic.com/news/x", "evidence_text": "ev",
        "verification_status": config.VS_VERIFIED,
        "source_type": "official_current", "is_official": 1, "status": config.STATUS_CONFIRMED,
        "content_hash": ch, "created_at": now, "updated_at": now})


def test_export_skipped_when_unchanged(tmp_path):
    conn = _conn(tmp_path)
    _add_official(conn, 14, "2026-02-12", "h1")
    r1 = dashboard.write_if_changed(conn, tmp_path / "d.json")
    r2 = dashboard.write_if_changed(conn, tmp_path / "d.json")
    assert r1["changed"] is True and r1["written"] is True
    assert r2["changed"] is False and r2["written"] is False   # 데이터 안 바뀜 → export 생략
    # 데이터 바뀌면 다시 export
    _add_official(conn, 47, "2026-05-28", "h2")
    r3 = dashboard.write_if_changed(conn, tmp_path / "d.json")
    assert r3["changed"] is True


def test_discovery_registers_candidate_no_promotion(tmp_path):
    conn = _conn(tmp_path)
    # 알려지지 않은 도메인 → source_candidates 등록(자동 승격 X)
    ingest._register_source_candidate(conn, "https://some-new-blog.example/post", relevant=True)
    ingest._register_source_candidate(conn, "https://some-new-blog.example/post2", relevant=True)
    row = db.fetchone(conn, "SELECT * FROM source_candidates WHERE domain='some-new-blog.example'")
    assert row is not None
    assert row["status"] == "candidate"          # 자동 승격 안 함
    assert row["recommended_tier"] is None
    assert row["discovery_count"] == 2
    # 이미 알려진 도메인(anthropic.com=Tier A)은 후보로 등록하지 않음
    ingest._register_source_candidate(conn, "https://www.anthropic.com/news/x", relevant=True)
    assert db.fetchone(conn, "SELECT COUNT(*) FROM source_candidates")[0] == 1
