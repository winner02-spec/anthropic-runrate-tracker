# -*- coding: utf-8 -*-
"""텍스트에서 금액 후보 추출 → USD billion 표준화 + qualifier 판정.

규칙(스펙):
· $14B → exact
· about/approximately/around/roughly/~ $14B → approximately
· more than / over / at least / north of / surpass(ed) / exceed / $14B+ → over
· $20B–$26B / $20B to $26B → range (low, high)
· targeting / target of / aims for / goal of → target
· million 은 /1000 로 billion 환산. original_value/unit 은 원문 보존.
'$30B 이상' 을 정확한 $30B 로 저장하지 않음: value_low=30, value_high=None, qualifier=over.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

# 단위 → USD billion 환산 계수
_UNIT_TO_BN = {
    "b": 1.0, "bn": 1.0, "billion": 1.0, "billions": 1.0,
    "m": 0.001, "mn": 0.001, "million": 0.001, "millions": 0.001,
    "t": 1000.0, "tn": 1000.0, "trillion": 1000.0,
}
_UNIT_CANON = {
    "b": "billion", "bn": "billion", "billion": "billion", "billions": "billion",
    "m": "million", "mn": "million", "million": "million", "millions": "million",
    "t": "trillion", "tn": "trillion", "trillion": "trillion",
}

_NUM = r"\d{1,4}(?:,\d{3})*(?:\.\d+)?"
_UNIT = r"(?:billion|billions|bn|b|million|millions|mn|m|trillion|tn|t)"

# 범위: $20B–$26B / $20 to $26 billion / 20-26 billion
_RANGE_RE = re.compile(
    rf"\$?\s*({_NUM})\s*(?:{_UNIT})?\s*(?:–|—|-|to|~)\s*\$?\s*({_NUM})\s*({_UNIT})",
    re.IGNORECASE,
)
# 단일: (부호/수식어는 문맥에서 별도 판정) $14 billion / $14B / 14 billion
_SINGLE_RE = re.compile(rf"\$?\s*({_NUM})\s*({_UNIT})\b\+?", re.IGNORECASE)

_OVER_WORDS = ("more than", "over", "at least", "north of", "surpass", "surpassed",
               "exceed", "exceeded", "crossed", "above", "upward of", "topped")
_APPROX_WORDS = ("about", "approximately", "around", "roughly", "nearly", "~", "close to", "almost")
_TARGET_WORDS = ("target", "targeting", "aims for", "aiming", "goal of", "goal", "projected",
                 "projecting", "forecast", "expects", "expected to reach", "on track to",
                 "hopes to", "plans to reach")


def _to_bn(num: float, unit: str) -> float:
    return round(num * _UNIT_TO_BN[unit.lower()], 6)


def _clean_num(s: str) -> float:
    return float(s.replace(",", ""))


@dataclass
class MoneyCandidate:
    value_low_usd_bn: float
    value_high_usd_bn: float | None
    original_value: str
    original_unit: str            # billion/million/trillion (원문 정규화)
    qualifier: str                # exact|approximately|over|range|target
    span: tuple[int, int]
    context: str = ""
    original_currency: str = "USD"


def _qualifier_from_context(prefix: str, matched: str) -> str:
    p = prefix.lower()
    if matched.rstrip().endswith("+"):
        return "over"
    for w in _TARGET_WORDS:
        if w in p:
            return "target"
    for w in _OVER_WORDS:
        if w in p:
            return "over"
    for w in _APPROX_WORDS:
        if w in p:
            return "approximately"
    return "exact"


def extract_money(text: str, window: int = 48) -> list[MoneyCandidate]:
    """금액 후보 리스트. 범위를 우선 매칭하고, 겹치지 않는 단일값을 추가."""
    if not text:
        return []
    out: list[MoneyCandidate] = []
    taken: list[tuple[int, int]] = []

    # 1) 범위
    for m in _RANGE_RE.finditer(text):
        lo, hi, unit = m.group(1), m.group(2), m.group(3)
        prefix = text[max(0, m.start() - window):m.start()]
        out.append(MoneyCandidate(
            value_low_usd_bn=_to_bn(_clean_num(lo), unit),
            value_high_usd_bn=_to_bn(_clean_num(hi), unit),
            original_value=m.group(0).strip(),
            original_unit=_UNIT_CANON[unit.lower()],
            qualifier="range",
            span=(m.start(), m.end()),
            context=text[max(0, m.start() - window):min(len(text), m.end() + window)].strip(),
        ))
        taken.append((m.start(), m.end()))

    # 2) 단일값 (범위와 겹치지 않는 것만)
    for m in _SINGLE_RE.finditer(text):
        if any(m.start() < b and m.end() > a for (a, b) in taken):
            continue
        num, unit = m.group(1), m.group(2)
        prefix = text[max(0, m.start() - window):m.start()]
        q = _qualifier_from_context(prefix, m.group(0))
        out.append(MoneyCandidate(
            value_low_usd_bn=_to_bn(_clean_num(num), unit),
            value_high_usd_bn=None,
            original_value=m.group(0).strip(),
            original_unit=_UNIT_CANON[unit.lower()],
            qualifier=q,
            span=(m.start(), m.end()),
            context=text[max(0, m.start() - window):min(len(text), m.end() + window)].strip(),
        ))
    out.sort(key=lambda c: c.span[0])
    return out


# ── 문맥 판정(엄격) — 반드시 숫자 인접(로컬 컨텍스트)에서만 판단 ──
# run-rate 매출을 가리키는 명시적 표현(숫자 옆). 'arr' 은 단어경계로만(부분문자열 오탐 방지).
_RUNRATE_PHRASES = ("run rate", "run-rate", "runrate", "annualized revenue",
                    "annualised revenue", "revenue run rate", "revenue run-rate",
                    "annual run rate", "annualized run rate", "run-rate revenue",
                    "run rate revenue", "annualized sales")


def has_runrate_phrase(text: str) -> bool:
    t = (text or "").lower()
    if any(p in t for p in _RUNRATE_PHRASES):
        return True
    return re.search(r"\bARR\b", text or "") is not None  # ARR 은 대문자 단어경계로만


# 매출 run-rate 가 아닌 금액(펀딩·기부·밸류·투자·토큰·예산 등) → 제외
# 매출 run-rate 가 아닌 금액 신호(숫자 인접). 'series X'(라운드명)은 제목에도 흔해 제외어에서 뺌
# — 펀딩액은 fund/funding/raise/invest 등으로 이미 배제됨.
_EXCLUDE_WORDS = ("fund", "funding", "raise", "raised", "raising", "valuation", "valuing",
                  "valued at", "invest", "investment", "investor", "donat", "donation",
                  "commit", "committing", "grant", "pledge", "token", "budget",
                  "compute deal", "credits", "support to")


def is_excluded_context(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _EXCLUDE_WORDS)


# 제품 개별 수치(전사 run-rate 아님)
_PRODUCT_NAMES = ("claude code", "claude opus", "claude sonnet", "claude haiku",
                  "claude api", "claude for", "claude enterprise", "cowork", "claude cowork")


def product_in_context(text: str):
    t = (text or "").lower()
    for p in _PRODUCT_NAMES:
        if p in t:
            return p
    return None


# 회고/재인용(과거 수치) 신호 → 현재값으로 확정 금지
_RETRO_WORDS = ("up from", "from $", "from about", "previously", "a year ago", "last year",
                "grew from", "doubled from", "compared to", "was $", "이전", "전년", "지난해")


def is_retrospective(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _RETRO_WORDS)


# 회사(Anthropic) 전사 지표 여부 힌트
def mentions_anthropic(text: str) -> bool:
    return "anthropic" in (text or "").lower() or "our run" in (text or "").lower() or "we " in (text or "").lower()


# 하위호환: 기존 호출부용(로컬 컨텍스트 엄격 판정으로 위임)
def is_runrate_context(text: str) -> bool:
    return has_runrate_phrase(text) and not is_excluded_context(text)
