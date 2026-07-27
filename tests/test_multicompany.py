# -*- coding: utf-8 -*-
"""다중 회사(Anthropic+OpenAI) 구조 필수 검증(스펙 §10)."""
from tracker import config, dedup
from tracker.database import db
from tracker.export import dashboard


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    return conn


def _rr(conn, cid, **kw):
    now = db.now_kst()
    row = {"company_id": cid, "metric_scope": config.SCOPE_COMPANY,
           "metric_type": config.MT_RUNRATE, "qualifier": "exact",
           "as_of_start": kw.get("as_of"), "as_of_end": kw.get("as_of"),
           "published_at": kw.get("as_of"), "source_url": "https://x.example/a",
           "evidence_text": "ev", "verification_status": config.VS_VERIFIED,
           "status": config.STATUS_CONFIRMED, "is_official": 0, "is_estimate": 0,
           "is_target": 0, "is_derived": 0, "created_at": now, "updated_at": now}
    row.update({k: v for k, v in kw.items() if k != "as_of"})
    slug = db.fetchone(conn, "SELECT slug FROM companies WHERE id=?", (cid,))[0]
    base = dedup.company_content_hash(slug, row["source_url"], "t", row["published_at"],
                                      row.get("value_low_usd_bn"), None, row["qualifier"], "ev")
    row["content_hash"] = kw.get("content_hash", base)
    return db.insert(conn, "runrate_updates", row)


def test_companies_seeded_on_migrate(tmp_path):
    conn = _conn(tmp_path)
    slugs = {r["slug"] for r in db.fetchall(conn, "SELECT slug FROM companies")}
    assert {"anthropic", "openai"} <= slugs


def test_cross_company_same_number_not_deduped(tmp_path):
    # 서로 다른 회사의 같은 숫자·같은 기사식별이라도 중복 처리되지 않는다
    conn = _conn(tmp_path)
    a = db.company_id_by_slug(conn, "anthropic")
    o = db.company_id_by_slug(conn, "openai")
    r1 = _rr(conn, a, value_low_usd_bn=20, is_official=1, metric_type=config.MT_ARR, as_of="2025-12-31")
    r2 = _rr(conn, o, value_low_usd_bn=20, is_official=1, metric_type=config.MT_ARR, as_of="2025-12-31")
    assert r1 is not None and r2 is not None and r1 != r2
    # content_hash 도 회사별로 달라 UNIQUE 충돌 없음
    hashes = [row[0] for row in conn.execute("SELECT content_hash FROM runrate_updates")]
    assert len(hashes) == len(set(hashes))


def test_monthly_not_classified_as_arr(tmp_path):
    conn = _conn(tmp_path)
    o = db.company_id_by_slug(conn, "openai")
    _rr(conn, o, value_low_usd_bn=20, is_official=1, metric_type=config.MT_ARR, qualifier="over", as_of="2025-12-31")
    _rr(conn, o, value_low_usd_bn=2, is_official=1, metric_type=config.MT_MONTHLY_REVENUE, as_of="2026-03-31")
    pl = dashboard.build_payload(conn, o, "openai", "OpenAI")
    # 월 매출은 공식(연환산) 선에 포함되지 않는다
    assert all(p["metric_type"] != config.MT_MONTHLY_REVENUE for p in pl["series"]["official"])
    assert len(pl["series"]["monthly"]) == 1
    # 최신 공식값 = ARR $20B (월매출 $2B 아님)
    assert pl["metrics"]["latest_official"]["value_low_usd_bn"] == 20


def test_derived_not_shown_as_official(tmp_path):
    conn = _conn(tmp_path)
    o = db.company_id_by_slug(conn, "openai")
    mid = _rr(conn, o, value_low_usd_bn=2, is_official=1, metric_type=config.MT_MONTHLY_REVENUE, as_of="2026-03-31")
    _rr(conn, o, value_low_usd_bn=24, is_official=0, is_derived=1, qualifier="derived",
        metric_type=config.MT_DERIVED_ANNUALIZED, calculation_method="monthly_revenue_x12",
        derived_from_id=mid, as_of="2026-03-31")
    pl = dashboard.build_payload(conn, o, "openai", "OpenAI")
    assert pl["series"]["official"] == []          # 파생은 공식선 미포함
    assert len(pl["series"]["derived"]) == 1
    assert pl["series"]["derived"][0]["is_derived"] == 1


def test_ads_pilot_arr_is_product_not_company(tmp_path):
    # ads pilot ARR($100M)은 product_metrics(product_arr)로 저장 → 전사 ARR 로 오분류되지 않음
    conn = _conn(tmp_path)
    o = db.company_id_by_slug(conn, "openai")
    now = db.now_kst()
    db.insert(conn, "product_metrics", {
        "company_id": o, "product": "ChatGPT Ads", "metric_name": "product_arr",
        "value_usd_bn": 0.1, "qualifier": "over", "as_of_date": "2026-03-31",
        "published_at": "2026-03-31", "source_url": "https://x.example/ads", "is_official": 1,
        "status": config.STATUS_CONFIRMED, "evidence_text": "ads pilot >$100M ARR",
        "content_hash": dedup.company_content_hash("openai", "https://x.example/ads", "ads",
                                                   "2026-03-31", 0.1, None, "over", "e"),
        "created_at": now})
    pl = dashboard.build_payload(conn, o, "openai", "OpenAI")
    assert pl["series"]["official"] == []                     # 전사 공식 ARR 아님
    assert len(pl["products"]) == 1 and pl["metrics"]["latest_official"] is None


def test_company_filter_isolates(tmp_path):
    conn = _conn(tmp_path)
    a = db.company_id_by_slug(conn, "anthropic")
    o = db.company_id_by_slug(conn, "openai")
    _rr(conn, a, value_low_usd_bn=47, is_official=1, metric_type=config.MT_RUNRATE, qualifier="over", as_of="2026-05-28")
    _rr(conn, o, value_low_usd_bn=20, is_official=1, metric_type=config.MT_ARR, qualifier="over", as_of="2025-12-31")
    pa = dashboard.build_payload(conn, a, "anthropic", "Anthropic")
    po = dashboard.build_payload(conn, o, "openai", "OpenAI")
    assert pa["metrics"]["latest_official"]["value_low_usd_bn"] == 47
    assert po["metrics"]["latest_official"]["value_low_usd_bn"] == 20
    assert len(pa["series"]["official"]) == 1 and len(po["series"]["official"]) == 1


def test_date_only_preserved(tmp_path):
    conn = _conn(tmp_path)
    o = db.company_id_by_slug(conn, "openai")
    _rr(conn, o, value_low_usd_bn=6, is_official=1, metric_type=config.MT_ARR, as_of="2024-12-31")
    pl = dashboard.build_payload(conn, o, "openai", "OpenAI")
    assert pl["series"]["official"][0]["as_of_end"] == "2024-12-31"   # 날짜 문자열 보존(하루 밀림 없음)
