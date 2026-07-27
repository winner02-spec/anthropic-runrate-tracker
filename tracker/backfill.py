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

    # company_id → slug 매핑(semantic_key 회사 분리용)
    cid_slug = {r["id"]: r["slug"] for r in db.fetchall(conn, "SELECT id, slug FROM companies")}

    # 재인용 중복 방지: 이미 있는 확정 포인트의 semantic_key(회사·값·기준일·공식여부)
    seen_semantic = set()
    for r in db.fetchall(conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,)):
        d = dict(r)
        slug = cid_slug.get(d.get("company_id"), "anthropic")
        seen_semantic.add(dedup.semantic_key(slug, d["metric_scope"], d["metric_type"],
                          d["value_low_usd_bn"], d["value_high_usd_bn"], d["qualifier"],
                          d["as_of_end"], d["is_official"], d["is_estimate"], d["is_target"]))

    points = _load_points()
    added = dup = skipped_filter = 0
    now = db.now_kst()
    ref_to_id: dict = {}   # yaml point 의 ref → 삽입된 runrate id(파생 observation 연결용)
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
        is_derived = int(p.get("is_derived", 0))
        metric_type = p.get("metric_type") or config.METRIC_RUNRATE
        metric_scope = p.get("metric_scope") or config.SCOPE_COMPANY
        # 파생 observation(월매출×12 등)은 공식 ARR 로 취급하지 않음
        is_official = 0 if is_derived else int(p.get("is_official", 0))
        # 회사 라우팅
        slug = (p.get("company") or "anthropic").strip().lower()
        comp = config.companies_config().get(slug, {})
        cid = db.ensure_company(conn, slug, comp.get("display_name") or slug.title(),
                                comp.get("official_domain"))
        # 계층형 검증상태(verified/corroborated/provisional/needs_review). 표시대상은 status=confirmed.
        vstatus = p.get("verification_status") or ("provisional" if is_estimate else "needs_review")
        status = (config.STATUS_CONFIRMED if vstatus in config.VS_SHOWN
                  else config.STATUS_NEEDS_REVIEW)
        # 외부추정 자동'승격' 방지: auto_approve=false 면 verified/corroborated 로 못 올리고 최대 provisional
        if is_estimate and not est_auto and vstatus in (config.VS_VERIFIED, config.VS_CORROBORATED):
            vstatus = config.VS_PROVISIONAL
        ch = dedup.company_content_hash(slug, p.get("source_url", ""), p.get("source_name", ""),
                                        p.get("published_at"), low, high, qualifier,
                                        p.get("evidence_text", ""))
        if db.exists_hash(conn, "runrate_updates", ch):
            dup += 1; continue
        # 같은 회사·수치·기준일·공식여부면(다른 출처 재인용) 새 포인트 만들지 않음
        sk = dedup.semantic_key(slug, metric_scope, metric_type, low, high, qualifier, as_of_end,
                                is_official, is_estimate, int(p.get("is_target", 0)))
        if status == config.STATUS_CONFIRMED and sk in seen_semantic:
            dup += 1; continue
        if dry_run:
            added += 1; seen_semantic.add(sk); continue
        derived_from_id = ref_to_id.get(p.get("derived_from")) if p.get("derived_from") else None
        row = {
            "company": comp.get("display_name") or slug.title(), "company_id": cid,
            "metric_scope": metric_scope,
            "metric_type": metric_type,
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
            "is_official": is_official,
            "is_estimate": is_estimate, "is_target": int(p.get("is_target", 0)),
            "is_derived": is_derived, "calculation_method": p.get("calculation_method"),
            "derived_from_id": derived_from_id,
            "verification_status": vstatus,
            "verification_reason": p.get("verification_reason"),
            "verified_at": now if vstatus == config.VS_VERIFIED else None,
            "source_note": p.get("source_note"), "evidence_note": p.get("evidence_note"),
            "source_locator": p.get("source_locator"),
            "content_hash": ch, "created_at": now, "updated_at": now,
        }
        rid = db.insert(conn, "runrate_updates", row)
        if rid is not None:
            added += 1
            seen_semantic.add(sk)
            if p.get("ref"):
                ref_to_id[p["ref"]] = rid
        else:
            dup += 1

    after = db.fetchone(conn, "SELECT COUNT(*) FROM runrate_updates")[0]
    return {"before": before, "after": after, "added": added, "duplicates": dup,
            "skipped_filter": skipped_filter, "points_total": len(points), "dry_run": dry_run}
