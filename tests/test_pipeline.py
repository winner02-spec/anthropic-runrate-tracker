# -*- coding: utf-8 -*-
from tracker.pipeline import build_candidates


def test_tier_a_official_auto_confirm():
    cs = build_candidates(
        title="Anthropic update",
        url="https://www.anthropic.com/news/series-g",
        text="Today, our run-rate revenue is $14 billion.",
        published_at="2026-02-12", source_name="Anthropic", tier="A")
    assert cs, "후보 없음"
    c = cs[0]
    assert c.is_official == 1 and c.is_estimate == 0
    assert c.status == "confirmed"
    assert c.value_low_usd_bn == 14
    assert c.content_hash


def test_tier_c_estimate_needs_review():
    cs = build_candidates(
        title="Anthropic revenue estimate",
        url="https://sacra.com/c/anthropic/",
        text="We estimate Anthropic run-rate revenue at about $20 billion.",
        published_at="2026-03-01", source_name="Sacra", tier="C")
    assert cs
    c = cs[0]
    assert c.is_estimate == 1 and c.is_official == 0
    assert c.status == "needs_review"


def test_funding_amount_not_treated_as_runrate():
    # run-rate 문맥이 아닌 펀딩 금액은 후보에서 제외
    cs = build_candidates(
        title="Anthropic raises money",
        url="https://www.anthropic.com/news/series-g",
        text="Anthropic raised $30 billion in Series G funding.",
        published_at="2026-02-12", source_name="Anthropic", tier="A")
    assert cs == []


def test_fund_donation_amount_excluded_even_if_runrate_word_in_doc():
    # 문서 어딘가 run-rate 언급이 있어도, 기부/펀딩 금액의 '로컬' 문맥엔 없으므로 제외
    cs = build_candidates(
        title="Economic Futures Fund",
        url="https://www.anthropic.com/news/economic-futures-research-fund-agenda",
        text=("Our annualized revenue run rate context appears elsewhere. "
              "We are committing $200 million to the fund and donating another $20 million."),
        published_at="2026-06-01", source_name="Anthropic", tier="A")
    assert all(abs((c.value_low_usd_bn or 0) - 0.2) > 1e-9 for c in cs)  # $200M 확정 안 됨
    assert all(c.status != "confirmed" or c.metric_scope == "company" for c in cs)


def test_token_budget_not_runrate():
    cs = build_candidates(
        title="Sonnet 5", url="https://www.anthropic.com/news/claude-sonnet-5",
        text="The system used a 10M token budget with compaction.",
        published_at="2026-06-01", source_name="Anthropic", tier="A")
    assert cs == []


def test_product_number_scoped_product_not_company():
    cs = build_candidates(
        title="Series G", url="https://www.anthropic.com/news/series-g",
        text="Claude Code's run-rate revenue has grown to over $2.5 billion.",
        published_at="2026-02-12", source_name="Anthropic", tier="A")
    assert cs
    c = cs[0]
    assert c.metric_scope == "product"       # 제품 개별수치 → 전사 아님
    assert c.status == "needs_review"        # 자동확정 안 함


def test_retrospective_number_needs_review():
    cs = build_candidates(
        title="Series H", url="https://www.anthropic.com/news/series-h",
        text="Our run-rate revenue crossed $47 billion, up from $9 billion at the end of 2025.",
        published_at="2026-05-28", source_name="Anthropic", tier="A")
    # 'up from $9 billion' 회고 수치는 확정 금지
    nine = [c for c in cs if abs((c.value_low_usd_bn or 0) - 9) < 1e-9]
    assert nine and all(c.status == "needs_review" for c in nine)


def test_multiple_timepoints_one_article():
    # 한 기사에 두 시점 수치 → 각각 별도 후보(현재 $47B + 회고 $9B)
    cs = build_candidates(
        title="Series H", url="https://www.anthropic.com/news/series-h",
        text="Our run-rate revenue crossed $47 billion, up from $9 billion at the end of 2025.",
        published_at="2026-05-28", source_name="Anthropic", tier="A")
    vals = sorted(c.value_low_usd_bn for c in cs)
    assert 9 in vals and 47 in vals   # 두 시점 모두 추출


def test_undated_not_auto_confirmed():
    cs = build_candidates(
        title="x", url="https://www.anthropic.com/news/x",
        text="Our run-rate revenue is $14 billion.",
        published_at=None, source_name="Anthropic", tier="A")
    assert cs and all(c.status == "needs_review" for c in cs)  # 발표일 없으면 자동확정 금지
