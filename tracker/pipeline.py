# -*- coding: utf-8 -*-
"""문서 → 후보(runrate_updates 행) 변환 파이프라인.

문서(title/url/text/published_at/source_name/tier) 를 받아:
숫자 추출 → 날짜 분리 → 공식/추정/목표 분류 → content_hash → 자동확정 or 검토큐 후보 생성.
숫자가 임의로 만들어지지 않도록, 텍스트에서 실제 추출된 표현만 후보로 만든다.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

from tracker import config, dedup
from tracker.extractors.numbers import (
    extract_money, has_runrate_phrase, is_excluded_context, product_in_context,
    is_retrospective, mentions_anthropic,
)
from tracker.extractors.dates import extract_as_of
from tracker.classifiers.statement import classify


@dataclass
class Candidate:
    metric_scope: str
    metric_type: str
    value_low_usd_bn: float
    value_high_usd_bn: float | None
    original_value: str
    original_currency: str
    original_unit: str
    qualifier: str
    as_of_start: str | None
    as_of_end: str | None
    date_precision: str
    display_date: str | None
    published_at: str | None
    source_name: str | None
    source_url: str | None
    source_tier: str | None
    source_type: str
    status: str
    confidence_score: float
    evidence_text: str
    is_official: int
    is_estimate: int
    is_target: int
    content_hash: str
    auto_confirmable: bool

    def to_row(self) -> dict:
        d = asdict(self)
        d.pop("auto_confirmable", None)
        d["is_official"] = int(self.is_official)
        d["is_estimate"] = int(self.is_estimate)
        d["is_target"] = int(self.is_target)
        return d


def _best_evidence(context: str) -> str:
    # context 를 근거 문장으로(짧게 보존). 전문 복제 금지 원칙 → 앞뒤 소량만.
    return (context or "").strip()[:280]


def build_candidates(*, title: str, url: str, text: str, published_at: str | None,
                     source_name: str, tier: str,
                     metric_scope: str = config.SCOPE_COMPANY,
                     metric_type: str = config.METRIC_RUNRATE) -> list[Candidate]:
    """한 문서에서 run-rate 관련 금액 후보들을 생성."""
    body = f"{title}. {text}" if title else (text or "")
    cands: list[Candidate] = []
    for money in extract_money(body):
        # 문장 수준 로컬 문맥(±140자) — 제품명/배제어/run-rate 문구 판정용(±48은 이름을 자름)
        s, e = money.span
        local = body[max(0, s - 140):min(len(body), e + 140)]
        # 1) run-rate 매출 표현이 '숫자 인접(로컬)'에 있어야 함(문서 전체 아님)
        if not has_runrate_phrase(local):
            continue
        # 2) 펀딩·기부·밸류·투자·토큰·예산 등은 매출 run-rate 아님 → 제외
        if is_excluded_context(local):
            continue
        # 3) 제품 개별수치(Claude Code 등)는 전사 run-rate 아님 → scope=product
        product = product_in_context(local)
        scope = config.SCOPE_PRODUCT if product else metric_scope
        # 4) 회고/재인용 과거수치 신호
        retro = is_retrospective(local)

        asof = extract_as_of(local, published_at)
        st = classify(tier, money.qualifier, local, runrate_context=True, retrospective=retro)
        evidence = _best_evidence(local)
        ch = dedup.content_hash(url, title, published_at,
                                money.value_low_usd_bn, money.value_high_usd_bn,
                                money.qualifier, evidence)

        # 자동확정(엄격): TierA official + 전사 scope + 발표일 존재 + 회고/목표 아님 + 회사 언급
        auto = bool(st.auto_confirmable and scope == config.SCOPE_COMPANY
                    and published_at and not retro and not st.is_target
                    and mentions_anthropic(local))
        status = config.STATUS_CONFIRMED if auto else config.STATUS_NEEDS_REVIEW
        cands.append(Candidate(
            metric_scope=scope, metric_type=metric_type,
            value_low_usd_bn=money.value_low_usd_bn,
            value_high_usd_bn=money.value_high_usd_bn,
            original_value=money.original_value,
            original_currency=money.original_currency,
            original_unit=money.original_unit,
            qualifier=money.qualifier,
            as_of_start=asof.start, as_of_end=asof.end, date_precision=asof.precision,
            display_date=(asof.end or asof.start or published_at),
            published_at=published_at,
            source_name=source_name, source_url=url, source_tier=tier,
            source_type=("product" if product else st.source_type), status=status,
            confidence_score=round(st.confidence, 3),
            evidence_text=evidence,
            is_official=int(st.is_official), is_estimate=int(st.is_estimate),
            is_target=int(st.is_target),
            content_hash=ch, auto_confirmable=auto,
        ))
    return cands
