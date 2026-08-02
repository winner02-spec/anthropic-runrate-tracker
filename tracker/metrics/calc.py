# -*- coding: utf-8 -*-
"""지표 계산. 공식 시계열끼리만 성장률을 기본 계산하고, qualifier(over/approx/range)는
정밀 단일값처럼 표시하지 않도록 라벨을 붙인다. 공식/추정은 절대 섞지 않는다.

입력 point(dict) 최소 필드:
  value_low_usd_bn, value_high_usd_bn, qualifier, as_of_end, is_official, is_estimate, is_target
"""
from __future__ import annotations
from datetime import date
from dateutil import parser as dparser

APPROX_QUALIFIERS = {"over", "approximately", "range", "target"}


def _d(s):
    try:
        return dparser.parse(str(s)).date()
    except (ValueError, TypeError):
        return None


def _repr_value(p: dict):
    """대표값: 범위면 하단, 아니면 low. (라벨로 불확실성 표시)"""
    return p.get("value_low_usd_bn")


def _sorted_official(points: list[dict]) -> list[dict]:
    offs = [p for p in points if p.get("is_official") and _d(p.get("as_of_end"))]
    return sorted(offs, key=lambda p: _d(p["as_of_end"]))


def _sorted_estimates(points: list[dict]) -> list[dict]:
    est = [p for p in points if p.get("is_estimate") and _d(p.get("as_of_end"))]
    return sorted(est, key=lambda p: _d(p["as_of_end"]))


def latest_official(points: list[dict]) -> dict | None:
    offs = _sorted_official(points)
    return offs[-1] if offs else None


def latest_estimate(points: list[dict]) -> dict | None:
    est = _sorted_estimates(points)
    return est[-1] if est else None


def estimate_source(p: dict) -> str:
    """추정 출처 표시명 → 기관명(괄호 앞). 예: 'TickerTrends (OpenAI ARR 추정)' → 'TickerTrends'."""
    name = (p.get("source_name") or "출처 미상").strip()
    return name.split("(")[0].strip() or name


def latest_estimates_by_source(points: list[dict]) -> list[dict]:
    """기관별 최신 외부추정(기준일 최신순). 기관이 다르면 하나의 시계열로 합치지 않는다."""
    by: dict[str, dict] = {}
    for p in _sorted_estimates(points):   # 기준일 오름차순 → 마지막이 기관별 최신
        by[estimate_source(p)] = p
    rows = [{"source": k, "point": v} for k, v in by.items()]
    return sorted(rows, key=lambda r: _d(r["point"]["as_of_end"]), reverse=True)


def estimate_divergence(points: list[dict]) -> dict | None:
    """기관별 최신 추정치의 편차(기관 2곳 이상일 때). 어느 쪽이 옳다고 판단하지 않는다."""
    rows = [(r["source"], _repr_value(r["point"]), r["point"].get("as_of_end"))
            for r in latest_estimates_by_source(points) if _repr_value(r["point"]) is not None]
    if len(rows) < 2:
        return None
    hi = max(rows, key=lambda t: t[1])
    lo = min(rows, key=lambda t: t[1])
    spread = round(hi[1] - lo[1], 3)
    return {
        "high": {"source": hi[0], "value_usd_bn": hi[1], "as_of": hi[2]},
        "low": {"source": lo[0], "value_usd_bn": lo[1], "as_of": lo[2]},
        "spread_usd_bn": spread,
        "spread_pct": round(spread / lo[1] * 100, 1) if lo[1] else None,
        "source_count": len(rows),
        "note": "기관별 산정 방법·기준일이 달라 편차가 발생합니다. 단일 선으로 연결하지 않으며, "
                "어느 추정이 맞는지 판단하지 않습니다(방법론 확인 필요).",
    }


def official_estimate_gap(points: list[dict]) -> dict | None:
    off = latest_official(points)
    est = latest_estimate(points)
    if not off or not est:
        return None
    ov, ev = _repr_value(off), _repr_value(est)
    if ov is None or ev is None:
        return None
    diff = round(ev - ov, 3)
    pct = round(diff / ov * 100, 2) if ov else None
    return {"official": ov, "estimate": ev, "diff_usd_bn": diff, "diff_pct": pct,
            "note": "추정치 - 마지막 공식값 차이(실제 확정 성장률 아님)",
            "official_as_of": off.get("as_of_end"), "estimate_as_of": est.get("as_of_end")}


def growth_velocity(points: list[dict]) -> dict | None:
    """공식 수치끼리 최근 구간 속도."""
    offs = _sorted_official(points)
    if len(offs) < 2:
        return None
    cur, prev = offs[-1], offs[-2]
    cv, pv = _repr_value(cur), _repr_value(prev)
    d1, d0 = _d(cur["as_of_end"]), _d(prev["as_of_end"])
    if None in (cv, pv, d1, d0):
        return None
    days = (d1 - d0).days or 1
    delta = round(cv - pv, 3)
    per30 = round(delta / days * 30, 3)
    implied_monthly_pct = round((cv / pv - 1) / days * 30 * 100, 2) if pv else None
    approx = cur.get("qualifier") in APPROX_QUALIFIERS or prev.get("qualifier") in APPROX_QUALIFIERS
    return {
        "delta_usd_bn": delta, "days": days,
        "delta_per_30d_usd_bn": per30, "implied_monthly_growth_pct": implied_monthly_pct,
        "from": prev["as_of_end"], "to": cur["as_of_end"],
        "is_approximate": approx,
        "label": "하한/범위 기준(정밀값 아님)" if approx else "공식값 기준",
    }


def acceleration(points: list[dict]) -> dict:
    offs = _sorted_official(points)
    if len(offs) < 3:
        return {"state": "insufficient_data", "note": "공식 3개 이상 필요"}

    def seg_speed(a, b):
        av, bv = _repr_value(a), _repr_value(b)
        da, db = _d(a["as_of_end"]), _d(b["as_of_end"])
        if None in (av, bv, da, db):
            return None
        days = (db - da).days or 1
        return (bv - av) / days * 30

    last = seg_speed(offs[-2], offs[-1])
    prev = seg_speed(offs[-3], offs[-2])
    if last is None or prev is None:
        return {"state": "insufficient_data"}
    if last > prev * 1.05:
        state = "accelerating"
    elif last < prev * 0.95:
        state = "decelerating"
    else:
        state = "stable"
    return {"state": state, "recent_per30": round(last, 3), "prior_per30": round(prev, 3)}


def target_progress(points: list[dict]) -> dict | None:
    targets = [p for p in points if p.get("is_target")]
    off = latest_official(points)
    if not targets or not off:
        return None
    tgt = sorted(targets, key=lambda p: _d(p.get("as_of_end")) or date.min)[-1]
    ov = _repr_value(off)
    lo, hi = tgt.get("value_low_usd_bn"), tgt.get("value_high_usd_bn")
    out = {"official": ov, "target_low": lo, "target_high": hi,
           "target_date": tgt.get("as_of_end"),
           "vs_target_low_pct": round(ov / lo * 100, 1) if (ov and lo) else None,
           "vs_target_high_pct": round(ov / hi * 100, 1) if (ov and hi) else None,
           "already_exceeded": bool(ov and lo and ov >= lo)}
    td = _d(tgt.get("as_of_end"))
    od = _d(off.get("as_of_end"))
    if td and od:
        out["days_to_target"] = (td - od).days
    return out


def valuation_multiple(runrate_points: list[dict], valuations: list[dict],
                       max_gap_days: int = 120) -> dict | None:
    off = latest_official(runrate_points)
    if not off or not valuations:
        return None
    vals = [v for v in valuations if v.get("is_official") and _d(v.get("as_of_date"))]
    if not vals:
        return None
    v = sorted(vals, key=lambda x: _d(x["as_of_date"]))[-1]
    rr = _repr_value(off)
    val = v.get("valuation_usd_bn")
    if not rr or not val:
        return None
    gap_days = None
    od, vd = _d(off.get("as_of_end")), _d(v.get("as_of_date"))
    if od and vd:
        gap_days = abs((od - vd).days)
    out = {"valuation_usd_bn": val, "runrate_usd_bn": rr,
           "multiple": round(val / rr, 1), "basis": "official",
           "valuation_as_of": v.get("as_of_date"), "runrate_as_of": off.get("as_of_end"),
           "date_gap_days": gap_days,
           "date_mismatch_warning": bool(gap_days is not None and gap_days > max_gap_days)}
    return out


def normalized_series(points: list[dict], anchor: str = "2025-01-01") -> list[dict]:
    """공식 시계열을 공통 시작점(anchor) 기준 100 으로 정규화(회사간 성장 비교).
    base = anchor 이후 첫 공식값(없으면 전체 첫 공식값). 각 점 index = value/base*100."""
    offs = _sorted_official(points)
    if not offs:
        return []
    ad = _d(anchor)
    base_pt = None
    for p in offs:
        d = _d(p.get("as_of_end"))
        if d and ad and d >= ad:
            base_pt = p
            break
    base_pt = base_pt or offs[0]
    base = _repr_value(base_pt)
    if not base:
        return []
    out = []
    for p in offs:
        v = _repr_value(p)
        if v is None:
            continue
        out.append({"as_of_end": p.get("as_of_end"), "value_usd_bn": v,
                    "index": round(v / base * 100, 1)})
    return out


# USD 매출성 제품지표만 전사 대비 share 계산(사용자수·구독자수 등은 $ 아님 → share 없음)
_REVENUE_PRODUCT_METRICS = {"revenue_run_rate", "arr", "product_arr", "monthly_revenue"}


def product_contribution(points: list[dict], product_metrics: list[dict]) -> list[dict]:
    off = latest_official(points)
    total = _repr_value(off) if off else None
    out = []
    for pm in product_metrics:
        pv = pm.get("value_usd_bn")
        mname = pm.get("metric_name")
        is_revenue = mname in _REVENUE_PRODUCT_METRICS
        share = round(pv / total * 100, 1) if (pv and total and is_revenue) else None
        out.append({"product": pm.get("product"), "metric_name": mname,
                    "value_usd_bn": pv, "qualifier": pm.get("qualifier"),
                    "unit": pm.get("unit"), "is_revenue": is_revenue,
                    "share_pct": share, "as_of": pm.get("as_of_date"),
                    "date_mismatch": bool(off and is_revenue and pm.get("as_of_date")
                                          and pm.get("as_of_date") != off.get("as_of_end"))})
    return out
