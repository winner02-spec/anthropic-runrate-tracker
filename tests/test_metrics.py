# -*- coding: utf-8 -*-
from tracker.metrics import calc

OFF1 = {"value_low_usd_bn": 14, "value_high_usd_bn": None, "qualifier": "exact",
        "as_of_end": "2026-02-12", "is_official": 1}
OFF2 = {"value_low_usd_bn": 47, "value_high_usd_bn": None, "qualifier": "over",
        "as_of_end": "2026-05-15", "is_official": 1}
EST = {"value_low_usd_bn": 20, "value_high_usd_bn": None, "qualifier": "estimate",
       "as_of_end": "2026-03-01", "is_estimate": 1}


def test_velocity_flags_qualifier():
    v = calc.growth_velocity([OFF1, OFF2])
    assert v["delta_usd_bn"] == 33
    assert v["is_approximate"] is True   # OFF2 qualifier=over → 정밀값 아님
    assert v["days"] > 0


def test_official_estimate_gap_separated():
    g = calc.official_estimate_gap([OFF1, OFF2, EST])
    # 공식 최신 47, 추정 최신 20 → diff = 20-47
    assert g["official"] == 47 and g["estimate"] == 20
    assert g["diff_usd_bn"] == -27


def test_latest_estimate_by_source_separated():
    # 기관이 다르면 하나의 시계열로 합치지 않고 기관별 최신값을 각각 유지
    tt_old = {"value_low_usd_bn": 33.0, "qualifier": "estimate", "as_of_end": "2026-05-30",
              "is_estimate": 1, "source_name": "TickerTrends (OpenAI ARR 추정)"}
    tt_new = {"value_low_usd_bn": 42.6, "qualifier": "estimate", "as_of_end": "2026-07-29",
              "is_estimate": 1, "source_name": "TickerTrends (OpenAI ARR 추정)"}
    sacra = {"value_low_usd_bn": 25, "qualifier": "estimate", "as_of_end": "2026-02-28",
             "is_estimate": 1, "source_name": "Sacra (OpenAI 매출 추정)"}
    funda = {"value_low_usd_bn": 49, "qualifier": "approximately", "as_of_end": "2026-07-28",
             "is_estimate": 1, "source_name": "Funda (Axios 2026-07-28 재인용, 원자료 미확인)",
             "date_precision": "unknown"}
    rows = calc.latest_estimates_by_source([tt_old, tt_new, sacra, funda])
    got = {r["source"]: r["point"]["value_low_usd_bn"] for r in rows}
    assert got == {"TickerTrends": 42.6, "Sacra": 25, "Funda": 49}   # 기관별 최신 1개씩
    assert rows[0]["source"] == "TickerTrends"                        # 기준일 최신순
    assert rows[0]["point"]["as_of_end"] == "2026-07-29"


def test_estimate_divergence_reports_spread_without_judging():
    tt = {"value_low_usd_bn": 42.6, "qualifier": "estimate", "as_of_end": "2026-07-29",
          "is_estimate": 1, "source_name": "TickerTrends (OpenAI ARR 추정)"}
    sacra = {"value_low_usd_bn": 25, "qualifier": "estimate", "as_of_end": "2026-02-28",
             "is_estimate": 1, "source_name": "Sacra (OpenAI 매출 추정)"}
    d = calc.estimate_divergence([tt, sacra])
    assert d["high"]["source"] == "TickerTrends" and d["low"]["source"] == "Sacra"
    assert d["spread_usd_bn"] == 17.6
    assert d["source_count"] == 2
    # 기관이 1곳뿐이면 편차를 만들지 않는다
    assert calc.estimate_divergence([tt]) is None


def test_acceleration_insufficient():
    assert calc.acceleration([OFF1, OFF2])["state"] == "insufficient_data"


def test_valuation_multiple_date_mismatch():
    vals_close = [{"as_of_date": "2026-05-01", "valuation_usd_bn": 380, "is_official": 1}]
    m = calc.valuation_multiple([OFF1, OFF2], vals_close)
    assert m["multiple"] == round(380 / 47, 1)
    assert m["date_mismatch_warning"] is False

    vals_far = [{"as_of_date": "2025-01-01", "valuation_usd_bn": 380, "is_official": 1}]
    m2 = calc.valuation_multiple([OFF1, OFF2], vals_far)
    assert m2["date_mismatch_warning"] is True   # 500일+ 차이


def test_target_progress():
    tgt = {"value_low_usd_bn": 70, "value_high_usd_bn": None, "qualifier": "target",
           "as_of_end": "2026-12-31", "is_target": 1}
    tp = calc.target_progress([OFF1, OFF2, tgt])
    assert tp["target_low"] == 70
    assert tp["already_exceeded"] is False


def test_product_contribution_date_mismatch():
    pc = calc.product_contribution([OFF2], [{"product": "Claude Code", "metric_name": "revenue_run_rate",
                                             "value_usd_bn": 2.5, "as_of_date": "2026-02-12"}])
    assert pc[0]["share_pct"] == round(2.5 / 47 * 100, 1)
    assert pc[0]["date_mismatch"] is True


def test_product_contribution_non_revenue_no_share():
    # 사용자수·구독자수 등 비매출 지표는 전사 대비 $ share 를 계산하지 않는다
    pc = calc.product_contribution([OFF2], [{"product": "ChatGPT", "metric_name": "active_users",
                                             "value_usd_bn": 0.9, "as_of_date": "2026-02-12"}])
    assert pc[0]["share_pct"] is None
    assert pc[0]["is_revenue"] is False
