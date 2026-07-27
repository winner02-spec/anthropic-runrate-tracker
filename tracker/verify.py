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


def verify_history(conn, gap_days: int = 90, record: bool = False) -> dict:
    rows = [dict(r) for r in db.fetchall(
        conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,))]
    issues: dict[str, list] = {
        "missing_gaps": [], "duplicate_points": [], "date_inversions": [],
        "same_date_conflicts": [], "official_estimate_mix": [], "qualifier_loss": [],
        "requote_duplicates": [],
    }

    official = sorted([r for r in rows if r.get("is_official") and _d(r.get("as_of_end"))],
                      key=lambda r: _d(r["as_of_end"]))
    # 누락 구간(공식 연속점 간 gap_days 초과)
    for a, b in zip(official, official[1:]):
        gap = (_d(b["as_of_end"]) - _d(a["as_of_end"])).days
        if gap > gap_days:
            issues["missing_gaps"].append(f"{a['as_of_end']}→{b['as_of_end']} ({gap}일)")

    # 날짜 역전(as_of_end < as_of_start, 또는 published_at < as_of_start)
    for r in rows:
        s, e, pub = _d(r.get("as_of_start")), _d(r.get("as_of_end")), _d(r.get("published_at"))
        if s and e and e < s:
            issues["date_inversions"].append(f"id{r['id']} as_of {r['as_of_start']}>{r['as_of_end']}")
        if pub and s and pub < s:
            issues["date_inversions"].append(f"id{r['id']} published {r['published_at']} < as_of_start {r['as_of_start']}")

    # official/estimate 혼입(한 행이 둘 다 플래그)
    for r in rows:
        if r.get("is_official") and r.get("is_estimate"):
            issues["official_estimate_mix"].append(f"id{r['id']}")

    # 같은 날짜 상충(같은 as_of_end·같은 시계열인데 값이 다름) / 중복(값·날짜 동일)
    from collections import defaultdict
    by_key = defaultdict(list)
    for r in official:
        by_key[r["as_of_end"]].append(r)
    for d, group in by_key.items():
        vals = {r.get("value_low_usd_bn") for r in group}
        if len(group) > 1 and len(vals) > 1:
            issues["same_date_conflicts"].append(f"{d}: {sorted(v for v in vals if v is not None)}")
        elif len(group) > 1:
            issues["duplicate_points"].append(f"{d} x{len(group)} (값 {list(vals)[0]})")

    # 재인용 중복(값+기준일 동일, 출처만 다름) — official 아닌 것 포함
    seen = defaultdict(list)
    for r in rows:
        seen[(r.get("value_low_usd_bn"), r.get("as_of_end"), r.get("is_official"))].append(r.get("source_name"))
    for k, srcs in seen.items():
        if len(srcs) > 1:
            issues["requote_duplicates"].append(f"값{k[0]} {k[1]}: {srcs}")

    # qualifier 손실(원문에 +/over/about 있는데 exact 로 저장)
    for r in rows:
        ov = (r.get("original_value") or "")
        if r.get("qualifier") == "exact" and ("+" in ov or "over" in ov.lower() or "about" in ov.lower()):
            issues["qualifier_loss"].append(f"id{r['id']} '{ov}' → exact?")

    if record:
        now = db.now_kst()
        for typ, items in issues.items():
            for it in items:
                conn.execute("INSERT INTO anomaly_queue(anomaly_type, detail, detected_at, status) "
                             "VALUES(?,?,?, 'open')", (typ, it, now))
        conn.commit()

    total = sum(len(v) for v in issues.values())
    return {"total_issues": total, "issues": issues, "official_points": len(official)}
