# -*- coding: utf-8 -*-
from tracker.extractors.numbers import extract_money, is_runrate_context


def _one(text):
    cs = extract_money(text)
    assert cs, f"no candidate in {text!r}"
    return cs[0]


def test_billion_million_conversion():
    assert _one("run rate of $14 billion").value_low_usd_bn == 14
    assert _one("revenue of $500 million").value_low_usd_bn == 0.5
    assert _one("$14B run rate").value_low_usd_bn == 14


def test_exact():
    c = _one("run-rate revenue is $14 billion")
    assert c.qualifier == "exact"
    assert c.value_high_usd_bn is None


def test_over_variants():
    for t in ["more than $30 billion", "over $30B", "surpassed $30 billion",
              "crossed $30 billion", "$30B+ run rate"]:
        c = _one(t)
        assert c.qualifier == "over", t
        assert c.value_low_usd_bn == 30
        assert c.value_high_usd_bn is None  # $30B 이상을 정확 $30B 로 저장하지 않음


def test_approximately():
    for t in ["about $14 billion", "approximately $14B", "roughly $14 billion", "~$14B"]:
        assert _one(t).qualifier == "approximately", t


def test_approaching():
    for t in ["approaching $50 billion", "nearing $50B", "nears $50 billion"]:
        assert _one(t).qualifier == "approaching", t
    # 'approaching'을 approximately/exact 로 뭉개지 않음
    assert _one("about $50B").qualifier == "approximately"


def test_range():
    c = _one("targeting revenue of $20B to $26 billion")
    # target 언어가 있어도 범위는 range 우선(양끝 보존)
    assert c.qualifier in ("range", "target")
    c2 = _one("$20 billion to $26 billion")
    assert c2.qualifier == "range"
    assert c2.value_low_usd_bn == 20 and c2.value_high_usd_bn == 26


def test_target():
    c = _one("the company is targeting $20 billion in revenue")
    assert c.qualifier == "target"
    assert c.value_low_usd_bn == 20


def test_original_preserved():
    c = _one("$14 billion run rate")
    assert "14" in c.original_value
    assert c.original_unit == "billion"


def test_runrate_context():
    assert is_runrate_context("annualized revenue run rate of $14B")
    assert not is_runrate_context("raised $30 billion in Series G funding")
