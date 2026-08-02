# -*- coding: utf-8 -*-
"""health check + 이상 탐지(item 13). 이상은 자동 삭제/수정하지 않고 anomaly_queue 에 남긴다.
외부 기사 본문 재분석은 하지 않는다(비용 0)."""
from __future__ import annotations
import json
from datetime import date

from tracker import config
from tracker.database import db
from tracker.metrics import calc
from tracker import verify


def _points(conn):
    return [dict(r) for r in db.fetchall(
        conn, "SELECT * FROM runrate_updates WHERE status=?", (config.STATUS_CONFIRMED,))]


# 연환산 공식선(파생·월매출 제외 → 회사 지표 왜곡 방지)
_ANNUALIZED = (config.MT_ARR, config.MT_RUNRATE)

# 기관간 추정 격차를 안내(estimate_dispersion)로 남기는 최소 편차(%)
DISPERSION_PCT = 20.0


def _date_clear(p: dict) -> bool:
    """기준일이 명확한 포인트만 시계열 하락 계산에 사용(기준일 미상 추정 후보는 제외)."""
    return bool(p.get("as_of_end")) and (p.get("date_precision") or "day") != "unknown"


def detect_anomalies(conn, record: bool = True) -> list[dict]:
    all_pts = _points(conn)
    anomalies: list[dict] = []

    def add(typ, detail, company_id=None):
        anomalies.append({"type": typ, "detail": detail, "company_id": company_id})

    comps = {r["id"]: r["slug"] for r in db.fetchall(conn, "SELECT id, slug FROM companies")}
    for cid, slug in comps.items():
        pts = [p for p in all_pts if p.get("company_id") == cid]
        if not pts:
            continue
        # 연환산 공식만 지표에 사용(월매출·파생 제외)
        ann = [p for p in pts if not (p.get("metric_type") == config.MT_MONTHLY_REVENUE or p.get("is_derived"))]
        off = calc.latest_official(ann)
        est = calc.latest_estimate(pts)

        if off and off.get("as_of_end"):
            try:
                lag = (date.today() - date.fromisoformat(off["as_of_end"])).days
                if lag >= 90:
                    add("stale_90d", f"[{slug}] 최신 공식 {off['as_of_end']} ({lag}일 경과)", cid)
            except ValueError:
                pass
        if off and est and off.get("value_low_usd_bn") and est.get("value_low_usd_bn"):
            if est["value_low_usd_bn"] > off["value_low_usd_bn"] * 1.2:
                add("estimate_gap", f"[{slug}] 추정 {est['value_low_usd_bn']}({calc.estimate_source(est)}) "
                                    f"> 공식 {off['value_low_usd_bn']} +20%↑", cid)

        def series(pred, src=pts):
            xs = [p for p in src if pred(p) and p.get("as_of_end") and p.get("value_low_usd_bn") is not None]
            return sorted(xs, key=lambda p: p["as_of_end"])

        # ── 외부추정 하락(estimate_drop) ──
        # 같은 시계열 안에서만 비교한다: company_id · metric_type · source_name(=산정기관/방법론) 이 모두 같고
        # 기준일이 명확한(date_precision != unknown) 포인트끼리만. 기관이 다르면 '하락' 이 아니다.
        est_series: dict[tuple, list] = {}
        for p in series(lambda p: p.get("is_estimate")):
            if not _date_clear(p):
                continue
            est_series.setdefault((cid, p.get("metric_type"), calc.estimate_source(p)), []).append(p)
        for (_c, mtype, src_name), xs in est_series.items():
            if len(xs) >= 2 and xs[-1]["value_low_usd_bn"] < xs[-2]["value_low_usd_bn"]:
                add("estimate_drop",
                    f"[{slug}] {src_name}/{mtype} {xs[-2]['as_of_end']} {xs[-2]['value_low_usd_bn']} "
                    f"→ {xs[-1]['as_of_end']} {xs[-1]['value_low_usd_bn']}", cid)

        # ── 기관간 추정 격차(estimate_dispersion) ──
        # 오류가 아니라 '방법론·기준일이 다르다' 는 안내용. 자동 오류로 취급하지 않는다.
        disp = calc.estimate_divergence(pts)
        if disp and disp.get("spread_pct") is not None and disp["spread_pct"] >= DISPERSION_PCT:
            add("estimate_dispersion",
                f"[{slug}] 기관간 추정 격차 {disp['high']['source']} {disp['high']['value_usd_bn']}"
                f"({disp['high']['as_of']}) ↔ {disp['low']['source']} {disp['low']['value_usd_bn']}"
                f"({disp['low']['as_of']}) · 차이 {disp['spread_usd_bn']}({disp['spread_pct']}%) "
                f"· {disp['source_count']}개 기관 · 오류 아님(산정 방법론 차이 안내)", cid)

        off_s = series(lambda p: p.get("is_official"), ann)
        if len(off_s) >= 2 and off_s[-1]["value_low_usd_bn"] < off_s[-2]["value_low_usd_bn"]:
            add("lower_official", f"[{slug}] {off_s[-2]['value_low_usd_bn']} → {off_s[-1]['value_low_usd_bn']}", cid)
        acc = calc.acceleration(ann)
        if acc.get("state") in ("accelerating", "decelerating"):
            add("accel", f"[{slug}] {acc['state']} (recent {acc.get('recent_per30')} / prior {acc.get('prior_per30')})", cid)

    # verify-history 항목(회사별로 이미 분리·검사됨)
    vh = verify.verify_history(conn)
    for typ in ("date_inversions", "same_date_conflicts", "official_estimate_mix",
                "qualifier_loss", "requote_duplicates"):
        for it in vh["issues"].get(typ, []):
            add(typ, it)

    if record and anomalies:
        now = db.now_kst()
        for a in anomalies:
            # 동일 이상 중복 적재 방지 — 이미 사람이 dismissed/reviewed 한 건은 다시 open 으로 살리지 않는다.
            exists = db.fetchone(conn, "SELECT 1 FROM anomaly_queue WHERE anomaly_type=? AND detail=? "
                                       "LIMIT 1", (a["type"], a["detail"]))
            if not exists:
                conn.execute("INSERT INTO anomaly_queue(company_id, anomaly_type, detail, detected_at, status) "
                             "VALUES(?,?,?,?, 'open')",
                             (a.get("company_id"), a["type"], a["detail"], now))
        conn.commit()
    return anomalies


def dismiss_anomaly(conn, anomaly_id: int, reason: str) -> dict | None:
    """오탐 정리 — 레코드를 삭제하지 않고 dismissed 로 남긴다.
    원 탐지값(anomaly_type/detail/detected_at/status)은 audit_json 에 그대로 보존한다."""
    row = db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (anomaly_id,))
    if row is None:
        return None
    d = dict(row)
    if d.get("status") == "dismissed":
        return d
    audit = {
        "original_status": d.get("status"),
        "original_anomaly_type": d.get("anomaly_type"),
        "original_detail": d.get("detail"),          # 기존 탐지값·비교 대상(원문 보존)
        "original_detected_at": d.get("detected_at"),
        "original_company_id": d.get("company_id"),
    }
    now = db.now_kst()
    conn.execute("UPDATE anomaly_queue SET status='dismissed', dismiss_reason=?, dismissed_at=?, "
                 "audit_json=? WHERE id=?",
                 (reason, now, json.dumps(audit, ensure_ascii=False), anomaly_id))
    conn.commit()
    return dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (anomaly_id,)))


def run_health(conn) -> dict:
    last = db.fetchone(conn, "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1")
    last_d = dict(last) if last else {}
    errs = []
    try:
        errs = json.loads(last_d.get("errors") or "[]")
    except Exception:
        errs = []
    review_pending = db.fetchone(conn, "SELECT COUNT(*) FROM review_queue WHERE status='pending'")[0]
    anomalies = detect_anomalies(conn, record=True)
    anom_open = db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue WHERE status='open'")[0]
    export_ready = config.DASHBOARD_JSON.exists()
    fp = db.fetchone(conn, "SELECT value FROM schema_meta WHERE key='data_fp'")
    return {
        "last_collect": last_d.get("finished_at"),
        "last_mode": last_d.get("mode"),
        "parser_errors": errs[:5],
        "review_queue_pending": review_pending,
        "anomalies_new": len(anomalies),
        "anomaly_queue_open": anom_open,
        "export_ready": export_ready,
        "deploy_fingerprint": fp["value"] if fp else None,
    }
