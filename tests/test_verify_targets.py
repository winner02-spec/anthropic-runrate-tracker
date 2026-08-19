# -*- coding: utf-8 -*-
"""verify-history 가 목표치를 관측치처럼 검사하지 않는다.

목표치는 앞날을 가리키는 것이 정의다. 2026년에 발표한 2028년 전망은 발표일이 대상 기간보다
앞서는데, 그건 어긋난 것이 아니라 당연한 것이다. 이걸 date_inversion 으로 세면 목표를 넣을
때마다 경고가 하나씩 늘고, 진짜 날짜 오류가 그 속에 묻힌다.
"""
from tracker import config, dedup, verify
from tracker.database import db


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    return conn


def _row(conn, cid, slug, *, as_of_start, as_of_end, published_at, is_target):
    now = db.now_kst()
    row = {
        "company_id": cid, "metric_scope": config.SCOPE_COMPANY,
        "metric_type": config.MT_TARGET if is_target else config.MT_RUNRATE,
        "value_low_usd_bn": 190.0, "qualifier": "range",
        "as_of_start": as_of_start, "as_of_end": as_of_end, "published_at": published_at,
        "source_url": "https://x.example/a", "evidence_text": "ev",
        "verification_status": config.VS_CORROBORATED, "status": config.STATUS_CONFIRMED,
        "is_official": 0, "is_estimate": 0, "is_target": 1 if is_target else 0,
        "is_derived": 0, "created_at": now, "updated_at": now,
    }
    row["content_hash"] = dedup.company_content_hash(
        slug, row["source_url"], f"t{is_target}", published_at, 190.0, None, "range", "ev")
    return db.insert(conn, "runrate_updates", row)


def test_a_forecast_about_a_future_year_is_not_a_date_inversion(tmp_path):
    conn = _conn(tmp_path)
    cid = db.ensure_company(conn, "anthropic", "Anthropic", None)
    _row(conn, cid, "anthropic", as_of_start="2028-01-01", as_of_end="2028-12-31",
         published_at="2026-08-14", is_target=True)

    assert verify.verify_history(conn)["issues"]["date_inversions"] == []


def test_an_observation_published_before_its_period_still_is(tmp_path):
    """관측치에는 이 검사가 그대로 살아 있어야 한다. 목표만 예외다."""
    conn = _conn(tmp_path)
    cid = db.ensure_company(conn, "anthropic", "Anthropic", None)
    _row(conn, cid, "anthropic", as_of_start="2028-01-01", as_of_end="2028-12-31",
         published_at="2026-08-14", is_target=False)

    assert len(verify.verify_history(conn)["issues"]["date_inversions"]) == 1


def test_a_reversed_period_is_still_caught_for_targets(tmp_path):
    """끝이 시작보다 앞서는 것은 목표라도 오류다. 예외는 발표일 쪽에만 둔다."""
    conn = _conn(tmp_path)
    cid = db.ensure_company(conn, "anthropic", "Anthropic", None)
    _row(conn, cid, "anthropic", as_of_start="2028-12-31", as_of_end="2028-01-01",
         published_at="2026-08-14", is_target=True)

    assert len(verify.verify_history(conn)["issues"]["date_inversions"]) == 1
