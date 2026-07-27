# -*- coding: utf-8 -*-
"""공식/보도/추정/목표 분류 + source_type 체계 + 플래그 + 신뢰도.

source_type:
· official_current        Tier A 공식 '현재값'
· official_retrospective  Tier A 공식자료가 회고한 '과거값'
· reported                주요 매체 자체 보도
· reported_company_statement  매체가 회사 공식발언을 재인용
· third_party_estimate    TickerTrends/Yipit/Sacra 등 외부추정 → Estimated 시계열 전용
· target                  목표치

자동확정(auto_confirmable)은 Tier A · 현재값(비회고) · 비목표 · run-rate 문맥일 때만.
"""
from __future__ import annotations
from dataclasses import dataclass

from tracker import config

_COMPANY_QUOTE = ("anthropic said", "anthropic announced", "the company said",
                  "in a statement", "spokesperson", "press release", "according to anthropic",
                  "ceo", "cfo", "dario amodei", "daniela amodei")
_TARGET_WORDS = ("target", "targeting", "goal", "aims", "aiming", "projected",
                 "forecast", "expects to reach", "on track to", "plans to reach")


@dataclass
class Statement:
    source_type: str
    is_official: bool
    is_estimate: bool
    is_target: bool
    auto_confirmable: bool
    confidence: float


def classify(tier: str, qualifier: str, text: str, runrate_context: bool,
             retrospective: bool = False) -> Statement:
    t = (text or "").lower()
    is_target = qualifier == "target" or any(w in t for w in _TARGET_WORDS)

    if is_target:
        conf = 0.7 if tier in ("A", "B") else 0.5
        return Statement(config.ST_TARGET, False, False, True, False, conf)

    if tier == "A":
        if retrospective:
            return Statement(config.ST_OFFICIAL_RETROSPECTIVE, True, False, False,
                             auto_confirmable=False, confidence=0.85)
        return Statement(config.ST_OFFICIAL_CURRENT, True, False, False,
                         auto_confirmable=runrate_context, confidence=0.92)

    if tier == "B":
        stype = (config.ST_REPORTED_COMPANY if any(w in t for w in _COMPANY_QUOTE)
                 else config.ST_REPORTED)
        return Statement(stype, False, False, False, auto_confirmable=False, confidence=0.6)

    if tier == "C":
        return Statement(config.ST_THIRD_PARTY_ESTIMATE, False, True, False,
                         auto_confirmable=False, confidence=0.45)

    # Tier D → 외부추정 취급하되 review 전용
    return Statement(config.ST_THIRD_PARTY_ESTIMATE, False, True, False,
                     auto_confirmable=False, confidence=0.25)
