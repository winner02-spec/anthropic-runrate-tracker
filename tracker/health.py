# -*- coding: utf-8 -*-
"""health check + 이상 탐지(item 13). 이상은 자동 삭제/수정하지 않고 anomaly_queue 에 남긴다.
외부 기사 본문 재분석은 하지 않는다(비용 0)."""
from __future__ import annotations
import hashlib
import json
import re
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


def anomaly_key(company_id, typ: str, metric_type=None, source=None, obs=()) -> str:
    """재계산 시 같은 이상을 같은 행으로 묶는 stable key.
    구성: company_id | anomaly_type | metric_type | source(기관/시계열) | 기준 observation id 들.
    값·경과일처럼 매 실행마다 바뀌는 값은 key 에 넣지 않는다(그래야 새 행이 안 생긴다)."""
    obs_part = ",".join(str(o) for o in obs if o is not None) or "-"
    return "|".join([str(company_id if company_id is not None else "-"), typ,
                     str(metric_type or "-"), str(source or "-"), obs_part])


def detect_anomalies(conn, record: bool = True) -> list[dict]:
    all_pts = _points(conn)
    anomalies: list[dict] = []

    def add(typ, detail, company_id=None, key=None, age_days=None):
        anomalies.append({"type": typ, "detail": detail, "company_id": company_id,
                          "key": key or anomaly_key(company_id, typ), "age_days": age_days})

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
                    # 상태 지속형 경고: 같은 공식 observation 이면 매일 새 행을 만들지 않고 갱신(age_days)
                    add("stale_90d", f"[{slug}] 최신 공식 {off['as_of_end']} ({lag}일 경과)", cid,
                        key=anomaly_key(cid, "stale_90d", off.get("metric_type"), "official",
                                        (off.get("id"),)),
                        age_days=lag)
            except ValueError:
                pass
        if off and est and off.get("value_low_usd_bn") and est.get("value_low_usd_bn"):
            if est["value_low_usd_bn"] > off["value_low_usd_bn"] * 1.2:
                # 같은 (공식 observation, 추정 observation) 조합이면 기존 레코드를 갱신
                add("estimate_gap", f"[{slug}] 추정 {est['value_low_usd_bn']}({calc.estimate_source(est)}) "
                                    f"> 공식 {off['value_low_usd_bn']} +20%↑", cid,
                    key=anomaly_key(cid, "estimate_gap", est.get("metric_type"),
                                    calc.estimate_source(est), (off.get("id"), est.get("id"))))

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
                    f"→ {xs[-1]['as_of_end']} {xs[-1]['value_low_usd_bn']}", cid,
                    key=anomaly_key(cid, "estimate_drop", mtype, src_name,
                                    (xs[-2].get("id"), xs[-1].get("id"))))

        # ── 기관간 추정 격차(estimate_dispersion) ──
        # 오류가 아니라 '방법론·기준일이 다르다' 는 안내용. 자동 오류로 취급하지 않는다.
        disp = calc.estimate_divergence(pts)
        if disp and disp.get("spread_pct") is not None and disp["spread_pct"] >= DISPERSION_PCT:
            by_src = {r["source"]: r["point"] for r in calc.latest_estimates_by_source(pts)}
            hi_p = by_src.get(disp["high"]["source"], {})
            lo_p = by_src.get(disp["low"]["source"], {})
            add("estimate_dispersion",
                f"[{slug}] 기관간 추정 격차 {disp['high']['source']} {disp['high']['value_usd_bn']}"
                f"({disp['high']['as_of']}) ↔ {disp['low']['source']} {disp['low']['value_usd_bn']}"
                f"({disp['low']['as_of']}) · 차이 {disp['spread_usd_bn']}({disp['spread_pct']}%) "
                f"· {disp['source_count']}개 기관 · 오류 아님(산정 방법론 차이 안내)", cid,
                key=anomaly_key(cid, "estimate_dispersion", None,
                                f"{disp['high']['source']}~{disp['low']['source']}",
                                (hi_p.get("id"), lo_p.get("id"))))

        off_s = series(lambda p: p.get("is_official"), ann)
        if len(off_s) >= 2 and off_s[-1]["value_low_usd_bn"] < off_s[-2]["value_low_usd_bn"]:
            add("lower_official", f"[{slug}] {off_s[-2]['value_low_usd_bn']} → {off_s[-1]['value_low_usd_bn']}", cid,
                key=anomaly_key(cid, "lower_official", off_s[-1].get("metric_type"), "official",
                                (off_s[-2].get("id"), off_s[-1].get("id"))))
        acc = calc.acceleration(ann)
        if acc.get("state") in ("accelerating", "decelerating"):
            off_ids = tuple(p.get("id") for p in off_s[-3:]) if len(off_s) >= 3 else ()
            add("accel", f"[{slug}] {acc['state']} (recent {acc.get('recent_per30')} / prior {acc.get('prior_per30')})",
                cid, key=anomaly_key(cid, "accel", None, "official", off_ids))

    # verify-history 항목(회사별로 이미 분리·검사됨). observation id 를 못 받으므로 detail 지문으로 key 고정.
    vh = verify.verify_history(conn)
    for typ in ("date_inversions", "same_date_conflicts", "official_estimate_mix",
                "qualifier_loss", "requote_duplicates"):
        for it in vh["issues"].get(typ, []):
            digest = hashlib.sha256(it.encode("utf-8")).hexdigest()[:16]
            add(typ, it, key=anomaly_key(None, typ, None, "verify_history", (digest,)))

    if record:
        record_anomalies(conn, anomalies)
    return anomalies


def record_anomalies(conn, anomalies: list[dict]) -> dict:
    """anomaly_key 기준 upsert. 같은 원인·같은 observation 이면 새 행을 만들지 않고 갱신한다.
    · open  → detail/last_seen_at/age_days/occurrence_count 갱신
    · dismissed/superseded/reviewed → 건드리지 않음(사람이 정리한 건을 되살리지 않음)"""
    now = db.now_kst()
    inserted = updated = skipped_resolved = 0
    for a in anomalies:
        key = a.get("key")
        row = db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE anomaly_key=? LIMIT 1", (key,))
        if row is None:
            # key 도입 이전(레거시) 행 흡수 — 같은 type+detail 이면 새 행 대신 그 행에 key 를 부여
            row = db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE anomaly_key IS NULL AND "
                                    "anomaly_type=? AND detail=? LIMIT 1", (a["type"], a["detail"]))
        if row is not None:
            d = dict(row)
            if d.get("status") != "open":
                skipped_resolved += 1
                continue
            conn.execute(
                "UPDATE anomaly_queue SET detail=?, last_seen_at=?, age_days=?, "
                "occurrence_count=COALESCE(occurrence_count,1)+1, "
                "anomaly_key=COALESCE(anomaly_key,?), company_id=COALESCE(company_id,?) WHERE id=?",
                (a["detail"], now, a.get("age_days"), key, a.get("company_id"), d["id"]))
            updated += 1
        else:
            conn.execute(
                "INSERT INTO anomaly_queue(company_id, anomaly_type, detail, detected_at, status, "
                "anomaly_key, last_seen_at, age_days, occurrence_count) VALUES(?,?,?,?, 'open', ?,?,?,1)",
                (a.get("company_id"), a["type"], a["detail"], now, key, now, a.get("age_days")))
            inserted += 1
    conn.commit()
    return {"detected": len(anomalies), "inserted": inserted, "updated": updated,
            "skipped_resolved": skipped_resolved}


def supersede_anomaly(conn, anomaly_id: int, kept_id: int, reason: str = "duplicate_recompute") -> dict | None:
    """중복 누적 정리 — 삭제하지 않고 superseded 로 남기고 살아남은 레코드를 가리킨다."""
    row = db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (anomaly_id,))
    if row is None:
        return None
    d = dict(row)
    if d.get("status") == "superseded":
        return d
    audit = _audit_base(d)
    audit.update({"superseded_by": kept_id, "supersede_reason": reason})
    now = db.now_kst()
    conn.execute("UPDATE anomaly_queue SET status='superseded', dismiss_reason=?, dismissed_at=?, "
                 "superseded_by=?, audit_json=? WHERE id=?",
                 (reason, now, kept_id, json.dumps(audit, ensure_ascii=False), anomaly_id))
    conn.commit()
    return dict(db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (anomaly_id,)))


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_GAP_RE = re.compile(r"추정\s*([\d.]+).*?공식\s*([\d.]+)")
_ACCEL_RE = re.compile(r"recent\s*(-?[\d.]+)\s*/\s*prior\s*(-?[\d.]+)")
_NUM_RE = re.compile(r"\d+\.\d+")     # 금액 표기($42.6B 등). 날짜·정수 카운트와 구분


def legacy_detail_fingerprint(d: dict) -> str:
    """anomaly_key 도입 이전 행을 '같은 이상'으로 묶기 위한 지문.
    경과일·출처 표기처럼 재계산마다 달라지는 부분은 빼고, 기준 observation 을 가리키는 값만 남긴다."""
    typ, detail = d.get("anomaly_type"), (d.get("detail") or "")
    if typ == "stale_90d":
        m = _DATE_RE.search(detail)
        return f"stale:{m.group(0) if m else detail}"
    if typ == "estimate_gap":
        m = _GAP_RE.search(detail)
        return f"gap:{m.group(1)}>{m.group(2)}" if m else detail
    if typ == "accel":
        m = _ACCEL_RE.search(detail)
        return f"accel:{m.group(1)}/{m.group(2)}" if m else detail
    return detail


def resolve_anomaly_owner(conn, row) -> dict | None:
    """anomaly 의 실제 소유 회사를 detail 문자열이 아니라 **연결 observation** 으로 재확인한다.
    회사별로 지표를 다시 계산해 그 회사의 observation 과 일치할 때만 소유자로 인정하고,
    후보가 0 곳이거나 2 곳 이상이면 None(수정하지 않음)."""
    d = dict(row)
    typ, detail = d.get("anomaly_type"), (d.get("detail") or "")
    all_pts = _points(conn)
    matches: list[dict] = []
    for c in db.fetchall(conn, "SELECT id, slug FROM companies"):
        cid, slug = c["id"], c["slug"]
        pts = [p for p in all_pts if p.get("company_id") == cid]
        if not pts:
            continue
        ann = [p for p in pts
               if not (p.get("metric_type") == config.MT_MONTHLY_REVENUE or p.get("is_derived"))]
        off = calc.latest_official(ann)
        ev = None
        if typ == "stale_90d":
            m = _DATE_RE.search(detail)
            if off and m and off.get("as_of_end") == m.group(0):
                ev = {"basis": "latest_official", "observation_id": off.get("id"),
                      "metric_type": off.get("metric_type"), "as_of_end": off.get("as_of_end")}
        elif typ == "estimate_gap":
            m = _GAP_RE.search(detail)
            est = calc.latest_estimate(pts)
            if m and off and est:
                ev_val, off_val = float(m.group(1)), float(m.group(2))
                hit = next((p for p in pts if p.get("is_estimate")
                            and p.get("value_low_usd_bn") == ev_val), None)
                if hit is not None and off.get("value_low_usd_bn") == off_val:
                    ev = {"basis": "official+estimate observation",
                          "official_observation_id": off.get("id"),
                          "estimate_observation_id": hit.get("id"),
                          "estimate_source": calc.estimate_source(hit),
                          "metric_type": hit.get("metric_type")}
        elif typ == "accel":
            m = _ACCEL_RE.search(detail)
            acc = calc.acceleration(ann)
            if m and acc.get("recent_per30") is not None:
                if (abs(acc["recent_per30"] - float(m.group(1))) < 1e-6
                        and abs(acc["prior_per30"] - float(m.group(2))) < 1e-6):
                    offs = [p for p in ann if p.get("is_official") and p.get("as_of_end")]
                    offs.sort(key=lambda p: p["as_of_end"])
                    ev = {"basis": "acceleration recomputed",
                          "observation_ids": [p.get("id") for p in offs[-3:]]}
        elif typ in ("estimate_drop", "estimate_dispersion", "lower_official"):
            # 비교 대상 두 값이 모두 이 회사의 observation 값으로 존재해야 소유자로 인정.
            # 날짜(2026-07-28)는 제거하고 소수점 표기 금액만 본다(연/월/일이 값으로 오인되지 않도록).
            nums = {float(x) for x in _NUM_RE.findall(_DATE_RE.sub(" ", detail))}
            hits = [p for p in pts if p.get("value_low_usd_bn") in nums]
            if len({p.get("value_low_usd_bn") for p in hits}) >= 2:
                ev = {"basis": "비교 대상 값이 모두 이 회사 observation 에 존재",
                      "observation_ids": [p.get("id") for p in hits]}
        if ev:
            matches.append({"company_id": cid, "slug": slug, "evidence": ev})
    if len(matches) != 1:
        return None
    return matches[0]


def correct_anomaly_ownership(conn, ids: list[int] | None = None, dry_run: bool = False) -> list[dict]:
    """일회성 migration — 레거시 일괄 backfill 로 잘못 채워진 anomaly.company_id 를
    연결 observation 기준으로 정정한다. 변경 전 값은 audit_json 에 보존한다."""
    sql = "SELECT * FROM anomaly_queue"
    args: tuple = ()
    if ids:
        sql += f" WHERE id IN ({','.join('?' * len(ids))})"
        args = tuple(ids)
    out = []
    now = db.now_kst()
    for row in db.fetchall(conn, sql + " ORDER BY id", args):
        d = dict(row)
        res = resolve_anomaly_owner(conn, d)
        if res is None:
            out.append({"id": d["id"], "action": "skipped", "reason": "소유 회사 확정 불가(후보 0 또는 2+)"})
            continue
        if d.get("company_id") == res["company_id"]:
            out.append({"id": d["id"], "action": "unchanged", "company_id": res["company_id"]})
            continue
        audit = _audit_base(d)
        audit.setdefault("original_company_id", d.get("company_id"))   # 기존 감사값 보존 우선
        audit.update({
            "corrected_company_id": res["company_id"],
            "correction_reason": "legacy_migration_company_mismatch",
            "corrected_at": now,
            "correction_evidence": res["evidence"],
        })
        if not dry_run:
            conn.execute("UPDATE anomaly_queue SET company_id=?, audit_json=? WHERE id=?",
                         (res["company_id"], json.dumps(audit, ensure_ascii=False), d["id"]))
        out.append({"id": d["id"], "action": "corrected", "from": d.get("company_id"),
                    "to": res["company_id"], "slug": res["slug"], "evidence": res["evidence"]})
    if not dry_run:
        conn.commit()
    return out


def _audit_base(d: dict) -> dict:
    """원 탐지값 보존용 감사 기록(기존 audit_json 이 있으면 이어붙인다)."""
    prev = {}
    if d.get("audit_json"):
        try:
            prev = json.loads(d["audit_json"])
        except (ValueError, TypeError):
            prev = {"unparsed_previous_audit": d["audit_json"]}
    base = {
        "original_status": d.get("status"),
        "original_anomaly_type": d.get("anomaly_type"),
        "original_detail": d.get("detail"),
        "original_detected_at": d.get("detected_at"),
        "original_company_id": d.get("company_id"),
    }
    base.update(prev)   # 기존 감사 기록은 덮어쓰지 않는다
    return base


def dismiss_anomaly(conn, anomaly_id: int, reason: str) -> dict | None:
    """오탐 정리 — 레코드를 삭제하지 않고 dismissed 로 남긴다.
    원 탐지값(anomaly_type/detail/detected_at/status)은 audit_json 에 그대로 보존한다."""
    row = db.fetchone(conn, "SELECT * FROM anomaly_queue WHERE id=?", (anomaly_id,))
    if row is None:
        return None
    d = dict(row)
    if d.get("status") == "dismissed":
        return d
    audit = _audit_base(d)   # 기존 탐지값·비교 대상(원문 보존)
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
    anomalies = detect_anomalies(conn, record=False)
    rec = record_anomalies(conn, anomalies)

    def _n(status):
        return db.fetchone(conn, "SELECT COUNT(*) FROM anomaly_queue WHERE status=?", (status,))[0]
    anom_open = _n("open")
    export_ready = config.DASHBOARD_JSON.exists()
    fp = db.fetchone(conn, "SELECT value FROM schema_meta WHERE key='data_fp'")
    return {
        "last_collect": last_d.get("finished_at"),
        "last_mode": last_d.get("mode"),
        "parser_errors": errs[:5],
        "review_queue_pending": review_pending,
        "anomalies_detected": rec["detected"],
        "anomalies_new": rec["inserted"],          # 신규 행(중복이면 0)
        "anomalies_updated": rec["updated"],       # 기존 open 행 갱신(last_seen_at/age_days)
        "anomalies_skipped_resolved": rec["skipped_resolved"],   # dismissed/superseded 는 되살리지 않음
        "anomaly_queue_open": anom_open,
        "anomaly_queue_dismissed": _n("dismissed"),
        "anomaly_queue_superseded": _n("superseded"),
        "export_ready": export_ready,
        "deploy_fingerprint": fp["value"] if fp else None,
    }
