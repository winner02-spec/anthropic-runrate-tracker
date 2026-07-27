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
    pc = calc.product_contribution([OFF2], [{"product": "Claude Code", "value_usd_bn": 2.5,
                                             "as_of_date": "2026-02-12"}])
    assert pc[0]["share_pct"] == round(2.5 / 47 * 100, 1)
    assert pc[0]["date_mismatch"] is True
