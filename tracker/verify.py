# -*- coding: utf-8 -*-
"""verify-history: 확정 시계열의 무결성 점검. 문제는 삭제/수정하지 않고 목록으로 보고
(+옵션으로 anomaly_queue 적재). 검사 항목:
누락 구간 · 중복 포인트 · 날짜 역전 · 같은 날짜 상충 값 · official/estimate 혼입 ·
qualifier 손실 · 재인용 중복.
"""
from __future__ import annotations
from datetime import date
from dateutil import parser as dp

from tracker import config
from tracker.database import db


def _d(s):
    try:
        return dp.parse(str(s)).date()
    except (ValueError, TypeError):
        return None


# 연환산 공식선(gap/conflict 분석 대상). 월매출·파생은 제외(스케일/성격이 달라 오탐 유발).
_ANNUALIZED = (config.MT_ARR, config.MT_RUNRATE)


def verify_history(conn, gap_days: int = 90, record: bool = False) -> dict:
    issues: dict[str, list] = {
        "missing_gaps": [], "duplicate_points": [], "date_inversions": [],
        "same_date_conflicts": [], "official_estimate_mix": [], "qualifier_loss": [],
        "requote_duplicates": [],
    }
    from collections import defaultdict
    comps = {r["id"]: r["slug"] for r in db.fetchall(conn, "SELECT id, slug FROM companies")}
    all_rows = [dict(r) for r in db.fetchall(
        conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,))]
    total_official = 0

    # ── 회사별로 검사(회사간 값/날짜를 섞어 오탐하지 않는다) ──
    for cid, slug in comps.items():
        rows = [r for r in all_rows if r.get("company_id") == cid]
        if not rows:
            continue
        # 연환산 공식선(월매출·파생 제외)
        official = sorted([r for r in rows if r.get("is_official") and not r.get("is_derived")
                           and r.get("metric_type") in _ANNUALIZED and _d(r.get("as_of_end"))],
                          key=lambda r: _d(r["as_of_end"]))
        total_official += len(official)
        for a, b in zip(official, official[1:]):
            gap = (_d(b["as_of_end"]) - _d(a["as_of_end"])).days
            if gap > gap_days:
                issues["missing_gaps"].append(f"[{slug}] {a['as_of_end']}→{b['as_of_end']} ({gap}일)")

        for r in rows:
            s, e, pub = _d(r.get("as_of_start")), _d(r.get("as_of_end")), _d(r.get("published_at"))
            if s and e and e < s:
                issues["date_inversions"].append(f"[{slug}] id{r['id']} as_of {r['as_of_start']}>{r['as_of_end']}")
            if pub and s and pub < s:
                issues["date_inversions"].append(f"[{slug}] id{r['id']} published {r['published_at']} < as_of_start {r['as_of_start']}")
            if r.get("is_official") and r.get("is_estimate"):
                issues["official_estimate_mix"].append(f"[{slug}] id{r['id']}")
            ov = (r.get("original_value") or "")
            if r.get("qualifier") == "exact" and ("+" in ov or "over" in ov.lower() or "about" in ov.lower()):
                issues["qualifier_loss"].append(f"[{slug}] id{r['id']} '{ov}' → exact?")

        by_key = defaultdict(list)
        for r in official:
            by_key[r["as_of_end"]].append(r)
        for d, group in by_key.items():
            vals = {r.get("value_low_usd_bn") for r in group}
            if len(group) > 1 and len(vals) > 1:
                issues["same_date_conflicts"].append(f"[{slug}] {d}: {sorted(v for v in vals if v is not None)}")
            elif len(group) > 1:
                issues["duplicate_points"].append(f"[{slug}] {d} x{len(group)} (값 {list(vals)[0]})")

        seen = defaultdict(list)
        for r in rows:
            seen[(r.get("value_low_usd_bn"), r.get("as_of_end"), r.get("is_official"))].append(r.get("source_name"))
        for k, srcs in seen.items():
            if len(srcs) > 1:
                issues["requote_duplicates"].append(f"[{slug}] 값{k[0]} {k[1]}: {srcs}")

    if record:
        now = db.now_kst()
        for typ, items in issues.items():
            for it in items:
                conn.execute("INSERT INTO anomaly_queue(anomaly_type, detail, detected_at, status) "
                             "VALUES(?,?,?, 'open')", (typ, it, now))
        conn.commit()

    total = sum(len(v) for v in issues.values())
    return {"total_issues": total, "issues": issues, "official_points": total_official}
