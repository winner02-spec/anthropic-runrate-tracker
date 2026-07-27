# -*- coding: utf-8 -*-
"""과거 시계열 backfill — config/backfill_sources.yml 의 '검증된 구조화 포인트'를 병합.

원칙:
· 원문·근거문장 확인된 것만 confirmed. 아니면 needs_review.
· content_hash 로 중복 방지 → 재실행 시 신규 0.
· 외부추정(estimates_*)은 settings.estimates.auto_approve=false 면 status를 needs_review 로 강등.
· current/retrospective·qualifier·기준일 범위(month_range)를 원문 그대로 보존.
"""
from __future__ import annotations
import yaml

from tracker import config, dedup
from tracker.database import db


def _load_points() -> list[dict]:
    try:
        data = yaml.safe_load(config.BACKFILL_SOURCES_YML.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return data.get("points", []) or []


def _num(v):
    if v is None or str(v).strip() == "":
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def run_backfill(conn, date_from: str | None = None, date_to: str | None = None,
                 source_filter: str | None = None, dry_run: bool = False) -> dict:
    settings = config.settings()
    est_auto = bool(settings.get("estimates", {}).get("auto_approve", False))
    before = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates")[0]

    # 재인용 중복 방지: 이미 있는 확정 포인트의 semantic_key(값·기준일·공식여부)
    seen_semantic = set()
    for r in db.fetchall(conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,)):
        d = dict(r)
        seen_semantic.add(dedup.semantic_key(d["metric_scope"], d["metric_type"],
                          d["value_low_usd_bn"], d["value_high_usd_bn"], d["qualifier"],
                          d["as_of_end"], d["is_official"], d["is_estimate"], d["is_target"]))

    points = _load_points()
    added = dup = skipped_filter = 0
    now = db.now_kst()
    for p in points:
        group = (p.get("group") or "").strip()
        # --source 필터: official | reuters | estimates(모든 estimates_*)
        if source_filter:
            if source_filter == "estimates":
                if not group.startswith("estimates"):
                    skipped_filter += 1; continue
            elif group != source_filter:
                skipped_filter += 1; continue
        as_of_end = p.get("as_of_end") or p.get("as_of_start")
        # --from/--to (as_of 기준)
        if date_from and as_of_end and as_of_end < date_from:
            skipped_filter += 1; continue
        if date_to and as_of_end and date_to != "today" and as_of_end > date_to:
            skipped_filter += 1; continue

        low = _num(p.get("value_low_usd_bn"))
        high = _num(p.get("value_high_usd_bn"))
        qualifier = p.get("qualifier") or "exact"
        is_estimate = int(p.get("is_estimate", 1 if group.startswith("estimates") else 0))
        # 계층형 검증상태(verified/corroborated/provisional/needs_review). 표시대상은 status=confirmed.
        vstatus = p.get("verification_status") or ("provisional" if is_estimate else "needs_review")
        status = (config.STATUS_CONFIRMED if vstatus in config.VS_SHOWN
                  else config.STATUS_NEEDS_REVIEW)
        # 외부추정 자동'승격' 방지: auto_approve=false 면 verified/corroborated 로 못 올리고 최대 provisional
        if is_estimate and not est_auto and vstatus in (config.VS_VERIFIED, config.VS_CORROBORATED):
            vstatus = config.VS_PROVISIONAL
        ch = dedup.content_hash(p.get("source_url", ""), p.get("source_name", ""),
                                p.get("published_at"), low, high, qualifier,
                                p.get("evidence_text", ""))
        if db.exists_hash(conn, "runrate_updates", ch):
            dup += 1; continue
        # 같은 수치·기준일·공식여부면(다른 출처 재인용) 새 포인트 만들지 않음
        sk = dedup.semantic_key(p.get("metric_scope") or config.SCOPE_COMPANY,
                                config.METRIC_RUNRATE, low, high, qualifier, as_of_end,
                                int(p.get("is_official", 0)), is_estimate, int(p.get("is_target", 0)))
        if status == config.STATUS_CONFIRMED and sk in seen_semantic:
            dup += 1; continue
        if dry_run:
            added += 1; seen_semantic.add(sk); continue
        row = {
            "company": p.get("company") or "Anthropic",
            "metric_scope": p.get("metric_scope") or config.SCOPE_COMPANY,
            "metric_type": config.METRIC_RUNRATE,
            "value_low_usd_bn": low, "value_high_usd_bn": high,
            "original_value": p.get("original_value") or (f"${low}B" if low else ""),
            "original_currency": "USD", "original_unit": "billion",
            "qualifier": qualifier,
            "as_of_start": p.get("as_of_start"), "as_of_end": as_of_end,
            "date_precision": p.get("date_precision") or "day",
            "display_date": as_of_end,
            "published_at": p.get("published_at"),
            "source_name": p.get("source_name"), "source_url": p.get("source_url"),
            "source_tier": p.get("source_tier") or ("A" if p.get("is_official") else "C"),
            "source_type": p.get("source_type") or ("third_party_estimate" if is_estimate else "official_current"),
            "status": status, "confidence_score": _num(p.get("confidence_score")) or 0.8,
            "evidence_text": p.get("evidence_text"),
            "is_official": int(p.get("is_official", 0)),
            "is_estimate": is_estimate, "is_target": int(p.get("is_target", 0)),
            "verification_status": vstatus,
            "verification_reason": p.get("verification_reason"),
            "verified_at": now if vstatus == config.VS_VERIFIED else None,
            "source_note": p.get("source_note"), "evidence_note": p.get("evidence_note"),
            "source_locator": p.get("source_locator"),
            "content_hash": ch, "created_at": now, "updated_at": now,
        }
        if db.insert(conn, "runrate_updates", row) is not None:
            added += 1
            seen_semantic.add(sk)
        else:
            dup += 1

    after = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates")[0]
    return {"before": before, "after": after, "added": added, "duplicates": dup,
            "skipped_filter": skipped_filter, "points_total": len(points), "dry_run": dry_run}
