# -*- coding: utf-8 -*-
"""SQLite → 정적 dashboard.json 생성(비밀 없음). 프론트가 이 JSON만 소비.

공식/추정/목표 시계열을 분리해 담는다(한 선으로 연결 금지는 프론트에서 처리).
확정(confirmed) 데이터만 시계열에 넣고, needs_review 는 품질 카운트로만 반영.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tracker import config
from tracker.database import db
from tracker.metrics import calc

_KST = ZoneInfo(config.TZ)


def _rows(conn, sql, args=()):
    return [dict(r) for r in db.fetchall(conn, sql, args)]


def _point(r: dict) -> dict:
    return {
        "value_low_usd_bn": r.get("value_low_usd_bn"),
        "value_high_usd_bn": r.get("value_high_usd_bn"),
        "qualifier": r.get("qualifier"),
        "as_of_start": r.get("as_of_start"), "as_of_end": r.get("as_of_end"),
        "date_precision": r.get("date_precision"),
        "published_at": r.get("published_at"),
        "source_name": r.get("source_name"), "source_url": r.get("source_url"),
        "source_tier": r.get("source_tier"), "source_type": r.get("source_type"),
        "confidence_score": r.get("confidence_score"),
        "evidence_text": r.get("evidence_text"),
        "is_official": r.get("is_official"), "is_estimate": r.get("is_estimate"),
        "is_target": r.get("is_target"),
        "verification_status": r.get("verification_status"),
        "verification_reason": r.get("verification_reason"),
        "source_note": r.get("source_note"), "evidence_note": r.get("evidence_note"),
        "source_locator": r.get("source_locator"),
    }


def build_payload(conn) -> dict:
    # 표시 대상 = verification_status ∈ (verified/corroborated/provisional). needs_review 제외.
    rows = _rows(
        conn,
        "SELECT * FROM runrate_updates WHERE metric_scope=? AND verification_status IN (?,?,?) "
        "ORDER BY as_of_end ASC",
        (config.SCOPE_COMPANY, config.VS_VERIFIED, config.VS_CORROBORATED, config.VS_PROVISIONAL),
    )
    prov_excluded = []
    official: list = []; estimated: list = []; targets: list = []; reported: list = []
    for r in rows:
        vs = r.get("verification_status")
        # provisional 인데 source_note/evidence_note 없으면 그 레코드만 제외(+경고)
        if vs == config.VS_PROVISIONAL and not (r.get("source_note") and r.get("evidence_note")):
            prov_excluded.append(f"id{r.get('id')} ${r.get('value_low_usd_bn')}B (note 누락)")
            continue
        p = _point(r)
        if r.get("is_target"):
            targets.append(p)
        elif r.get("is_estimate") or vs == config.VS_PROVISIONAL:
            estimated.append(p)                 # 외부추정·provisional → 공식선에 절대 미포함
        elif r.get("is_official"):
            official.append(p)                  # verified/corroborated 공식
        else:
            reported.append(p)                  # verified/corroborated 보도

    valuations = _rows(conn, "SELECT * FROM valuation_updates WHERE status=? ORDER BY as_of_date ASC",
                       (config.STATUS_CONFIRMED,))
    products = _rows(conn, "SELECT * FROM product_metrics WHERE status=? ORDER BY as_of_date ASC",
                     (config.STATUS_CONFIRMED,))
    events = _rows(conn, "SELECT * FROM source_events ORDER BY event_date ASC")

    all_points = official + estimated + targets
    # 최신 공식 카드는 verified 공식값만 사용(corroborated/provisional 제외)
    verified_official = [p for p in official if p.get("verification_status") == config.VS_VERIFIED]
    metrics = {
        "latest_official": calc.latest_official(verified_official),
        "latest_estimate": calc.latest_estimate(all_points),
        "official_estimate_gap": calc.official_estimate_gap(all_points),
        "growth_velocity": calc.growth_velocity(all_points),
        "acceleration": calc.acceleration(all_points),
        "target_progress": calc.target_progress(all_points),
        "valuation_multiple": calc.valuation_multiple(all_points, valuations),
        "product_contribution": calc.product_contribution(all_points, products),
    }

    # 데이터 품질
    def _count(sql, args=()):
        r = db.fetchone(conn, sql, args)
        return r[0] if r else 0

    last_run = db.fetchone(conn, "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1")
    def _vcount(vs):
        return _count("SELECT COUNT(*) FROM runrate_updates WHERE verification_status=?", (vs,))

    quality = {
        "official_count": len(official),
        "estimate_count": len(estimated),
        "target_count": len(targets),
        "verified_count": _vcount(config.VS_VERIFIED),
        "corroborated_count": _vcount(config.VS_CORROBORATED),
        "provisional_count": _vcount(config.VS_PROVISIONAL),
        "provisional_excluded": prov_excluded,   # note 누락으로 export 제외된 provisional
        "needs_review_count": _vcount(config.VS_NEEDS_REVIEW),
        "review_queue_count": _count("SELECT COUNT(*) FROM review_queue WHERE status='pending'"),
        "uncertain_asof_count": _count(
            "SELECT COUNT(*) FROM runrate_updates WHERE status=? AND "
            "(as_of_end IS NULL OR (as_of_start IS NOT NULL AND as_of_start <> as_of_end))",
            (config.STATUS_CONFIRMED,)),
        "last_collect": (dict(last_run).get("finished_at") if last_run else None),
        "last_errors": (json.loads(dict(last_run).get("errors") or "[]") if last_run else []),
    }

    freshness = {
        "latest_official_as_of": (verified_official[-1]["as_of_end"] if verified_official else None),
        "generated_kst": datetime.now(timezone.utc).astimezone(_KST).strftime("%Y-%m-%d %H:%M"),
    }

    return {
        "display_name": "Anthropic Revenue Run-rate Tracker",
        "note": "Revenue Run-rate 는 회계상 연간 매출과 다릅니다. 공식/추정 시계열은 분리 표시됩니다.",
        "series": {"official": official, "estimated": estimated, "reported": reported,
                   "target": targets},
        "valuations": valuations, "products": products, "events": events,
        "metrics": metrics, "quality": quality, "freshness": freshness,
    }


class ProvenanceError(Exception):
    """확정 관측치의 provenance 필수필드 누락 → export 차단."""


def validate_provenance(conn) -> None:
    """계층형 provenance 검사(item 6, 완화판):
    · verified: source_url·evidence_text·published_at 중 하나라도 없으면 실패
    · corroborated: source_note(확인매체)·evidence_note(근거) 중 하나라도 없으면 실패
    · provisional: 하드 요구 없음(source_url null 허용). note 누락은 build_payload 에서 해당 레코드만 제외.
    → provisional 미완성이 verified 전체 export 를 막지 않는다."""
    def has(d, f):
        return bool(d.get(f) and str(d.get(f)).strip())
    fail = []
    for r in db.fetchall(conn, "SELECT * FROM runrate_updates WHERE verification_status IN (?,?,?)",
                         (config.VS_VERIFIED, config.VS_CORROBORATED, config.VS_PROVISIONAL)):
        d = dict(r); vs = d.get("verification_status"); tag = f"id{d['id']}(${d.get('value_low_usd_bn')}B)"
        if vs == config.VS_VERIFIED:
            miss = [f for f in ("source_url", "evidence_text", "published_at") if not has(d, f)]
            if miss:
                fail.append(f"{tag} verified 누락 {miss}")
        elif vs == config.VS_CORROBORATED:
            miss = [f for f in ("source_note", "evidence_note") if not has(d, f)]
            if miss:
                fail.append(f"{tag} corroborated 누락 {miss}")
    if fail:
        raise ProvenanceError("provenance 검증 실패 → export 중단:\n  " + "\n  ".join(fail))


def write_dashboard(conn, path=None) -> str:
    validate_provenance(conn)
    payload = build_payload(conn)
    out = path or config.DASHBOARD_JSON
    config.ensure_dirs()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(out)


def _fingerprint(conn) -> str:
    """확정 데이터의 지문(변경 감지용). 데이터가 안 바뀌면 export/build/배포를 생략한다."""
    import hashlib
    parts = []
    for r in db.fetchall(conn, "SELECT value_low_usd_bn,value_high_usd_bn,qualifier,as_of_end,"
                               "source_type,is_official,is_estimate,is_target FROM runrate_updates "
                               "WHERE status=? ORDER BY as_of_end, value_low_usd_bn", (config.STATUS_CONFIRMED,)):
        parts.append("|".join(str(x) for x in tuple(r)))
    for r in db.fetchall(conn, "SELECT valuation_usd_bn,as_of_date FROM valuation_updates WHERE status=? ORDER BY as_of_date", (config.STATUS_CONFIRMED,)):
        parts.append("v|" + "|".join(str(x) for x in tuple(r)))
    for r in db.fetchall(conn, "SELECT product,value_usd_bn,as_of_date FROM product_metrics WHERE status=? ORDER BY as_of_date", (config.STATUS_CONFIRMED,)):
        parts.append("p|" + "|".join(str(x) for x in tuple(r)))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:32]


def write_if_changed(conn, path=None) -> dict:
    """확정 데이터가 실제로 바뀐 경우에만 dashboard.json 재생성. (item 7)"""
    fp = _fingerprint(conn)
    prev = db.fetchone(conn, "SELECT value FROM schema_meta WHERE key='data_fp'")
    prev_fp = prev["value"] if prev else None
    if fp == prev_fp:
        return {"changed": False, "written": False, "fingerprint": fp}
    out = write_dashboard(conn, path)
    conn.execute("INSERT INTO schema_meta(key,value) VALUES('data_fp',?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (fp,))
    conn.commit()
    return {"changed": True, "written": True, "path": out, "fingerprint": fp}
