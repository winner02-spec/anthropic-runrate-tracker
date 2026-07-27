# -*- coding: utf-8 -*-
"""공식/보도/추정/목표 분류 + is_official/is_estimate/is_target 플래그 + 신뢰도.

원칙:
· Tier A → official (target 언어면 target 병기). 자동 확정 후보.
· Tier B → reported (매체 보도). 공식 재인용이면 official 승격은 원문 확인 후에만.
· Tier C → estimate (외부 추정) → Estimated 시계열 전용.
· Tier D → social/unclear → review queue 만.
· qualifier=target 또는 target 언어 → is_target.
"""
from __future__ import annotations
from dataclasses import dataclass

_ESTIMATE_WORDS = ("estimate", "estimated", "estimates", "we think", "our model",
                   "implied", "projection by", "according to data")
_TARGET_WORDS = ("target", "targeting", "goal", "aims", "aiming", "projected",
                 "forecast", "expects to reach", "on track to", "plans to reach")
_OFFICIAL_ATTRIB = ("anthropic said", "anthropic announced", "the company said",
                    "in a statement", "spokesperson", "official", "press release",
                    "ceo", "cfo", "dario amodei", "daniela amodei")


@dataclass
class Statement:
    source_type: str        # official|reported|estimate|target|social
    is_official: bool
    is_estimate: bool
    is_target: bool
    auto_confirmable: bool  # Tier A + 명확 run-rate 표현일 때만
    confidence: float       # 0~1


def classify(tier: str, qualifier: str, text: str, runrate_context: bool) -> Statement:
    t = (text or "").lower()
    is_target = qualifier == "target" or any(w in t for w in _TARGET_WORDS)

    if tier == "A":
        stype = "target" if is_target else "official"
        conf = 0.9 if runrate_context else 0.75
        return Statement(stype, is_official=not is_target, is_estimate=False,
                         is_target=is_target,
                         auto_confirmable=(runrate_context and not is_target),
                         confidence=conf)

    if tier == "B":
        # 매체가 외부추정을 인용? estimate 언어면 estimate 로 강등
        if any(w in t for w in _ESTIMATE_WORDS):
            return Statement("estimate", False, True, is_target, False, 0.5)
        stype = "target" if is_target else "reported"
        return Statement(stype, is_official=False, is_estimate=False, is_target=is_target,
                         auto_confirmable=False, confidence=0.6)

    if tier == "C":
        return Statement("estimate", is_official=False, is_estimate=True,
                         is_target=is_target, auto_confirmable=False, confidence=0.45)

    # Tier D
    return Statement("social", is_official=False, is_estimate=False, is_target=is_target,
                     auto_confirmable=False, confidence=0.25)
