# -*- coding: utf-8 -*-
from tracker.database import db
from tracker.collectors import seed as seedmod

CSV = (
    "company,metric_scope,metric_type,value_low_usd_bn,value_high_usd_bn,original_value,"
    "original_currency,original_unit,qualifier,as_of_start,as_of_end,published_at,source_name,"
    "source_url,source_tier,source_type,status,confidence_score,evidence_text,is_official,"
    "is_estimate,is_target,content_hash\n"
    "Anthropic,company,revenue_run_rate,14,,$14 billion,USD,billion,exact,2026-02-12,2026-02-12,"
    "2026-02-12,Anthropic,https://www.anthropic.com/news/x,A,official,confirmed,0.95,evidence,1,0,0,\n"
)


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    return conn


def test_seed_no_duplicate_on_rerun(tmp_path):
    p = tmp_path / "runrate_updates.csv"
    p.write_text(CSV, encoding="utf-8")
    conn = _conn(tmp_path)
    first = seedmod.load_runrate_seed(conn, p)
    second = seedmod.load_runrate_seed(conn, p)
    assert first == 1
    assert second == 0   # 재실행 중복 방지
    cnt = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates")[0]
    assert cnt == 1


def test_official_estimate_stored_separately(tmp_path):
    conn = _conn(tmp_path)
    p = tmp_path / "runrate_updates.csv"
    p.write_text(CSV, encoding="utf-8")
    seedmod.load_runrate_seed(conn, p)
    off = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates WHERE is_official=1")[0]
    est = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates WHERE is_estimate=1")[0]
    assert off == 1 and est == 0
