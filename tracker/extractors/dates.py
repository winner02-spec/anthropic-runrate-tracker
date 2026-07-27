# -*- coding: utf-8 -*-
"""날짜 추출: published_at(게시일) 과 as_of(기준시점) 를 분리.

핵심: '5/28 발표에서 이달 초 47B 돌파' 처럼 게시일≠기준일 인 경우를 구분.
기준일이 불명확하면 월 단위 범위로 반환하고 uncertain=True 표시.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import date
from dateutil import parser as dparser
from calendar import monthrange

_MONTHS = ("january february march april may june july august september october "
           "november december").split()


def parse_published(value) -> str | None:
    """RSS/문자열 게시일 → 'YYYY-MM-DD'."""
    if not value:
        return None
    try:
        # feedparser struct_time(9-튜플) 지원
        if hasattr(value, "tm_year"):
            return date(value.tm_year, value.tm_mon, value.tm_mday).isoformat()
        return dparser.parse(str(value)).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass
class AsOf:
    start: str | None
    end: str | None
    uncertain: bool
    precision: str = "day"     # day | month_range | quarter | unknown
    note: str = ""


def _month_range(year: int, month: int) -> tuple[str, str]:
    last = monthrange(year, month)[1]
    return date(year, month, 1).isoformat(), date(year, month, last).isoformat()


def extract_as_of(text: str, published_at: str | None) -> AsOf:
    """텍스트의 시간 표현으로 기준시점 추정. 없으면 published_at 을 기준일로(확정)."""
    t = (text or "").lower()
    pub = None
    if published_at:
        try:
            pub = dparser.parse(published_at).date()
        except (ValueError, TypeError):
            pub = None

    # 1) 'earlier this month' / 'this month' → 월범위(불확실). 끝은 게시일(그 이전 시점이므로).
    if pub and ("earlier this month" in t or "this month" in t or "이달" in t):
        s = date(pub.year, pub.month, 1).isoformat()
        e = pub.isoformat()   # 'earlier' = 게시일 이전, 단정 없이 [월초, 게시일] 범위
        return AsOf(s, e, True, "month_range", "이달/earlier this month → 월범위(불확실)")

    # 2) 'last month' → 전월 범위
    if pub and "last month" in t:
        m = pub.month - 1 or 12
        y = pub.year if pub.month > 1 else pub.year - 1
        s, e = _month_range(y, m)
        return AsOf(s, e, True, "month_range", "last month → 전월범위")

    # 3) 'as of <Month> [year]' / 'in <Month> <year>'
    m = re.search(r"(?:as of|in|by|during)\s+(" + "|".join(_MONTHS) + r")\s*(\d{4})?", t)
    if m:
        mon = _MONTHS.index(m.group(1)) + 1
        yr = int(m.group(2)) if m.group(2) else (pub.year if pub else None)
        if yr:
            s, e = _month_range(yr, mon)
            return AsOf(s, e, True, "month_range", "월 명시 → 월범위")

    # 4) 명시적 날짜(YYYY-MM-DD 또는 Month D, YYYY)
    m2 = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2})", text or "")
    if m2:
        try:
            d = dparser.parse(m2.group(1)).date().isoformat()
            return AsOf(d, d, False, "day", "명시적 날짜")
        except (ValueError, TypeError):
            pass

    # 5) 시간 표현 없음 → 게시일을 기준일로(확정)
    if published_at:
        return AsOf(published_at, published_at, False, "day", "명시 표현 없음 → 게시일=기준일")
    return AsOf(None, None, True, "unknown", "날짜 불명확")
