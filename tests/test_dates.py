# -*- coding: utf-8 -*-
from tracker.extractors.dates import parse_published, extract_as_of


def test_parse_published_formats():
    assert parse_published("2026-02-12") == "2026-02-12"
    assert parse_published("Feb 12, 2026") == "2026-02-12"
    assert parse_published(None) is None


def test_published_vs_asof_separated():
    # 5/28 발표에서 'earlier this month crossed 47B' → 게시일≠기준일. '월 초'로 단정하지 않음.
    a = extract_as_of("run-rate revenue crossed $47 billion earlier this month", "2026-05-28")
    assert a.uncertain is True
    assert a.precision == "month_range"
    assert a.start == "2026-05-01"
    assert a.end == "2026-05-28"   # earlier = 게시일 이전 → [월초, 게시일] 범위(임의 단일일 아님)


def test_asof_defaults_to_published_when_no_cue():
    a = extract_as_of("our run-rate revenue is $14 billion", "2026-02-12")
    assert a.uncertain is False
    assert a.precision == "day"
    assert a.start == a.end == "2026-02-12"


def test_asof_month_mention():
    a = extract_as_of("as of March 2026 the figure was higher", "2026-04-10")
    assert a.uncertain is True
    assert a.precision == "month_range"
    assert a.start == "2026-03-01" and a.end == "2026-03-31"
