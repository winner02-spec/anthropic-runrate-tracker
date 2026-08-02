# -*- coding: utf-8 -*-
"""주간 다이제스트 — 지난 발송 이후 '외부 추정치 변화'만 짧게 보낸다.

원칙(요청 사양):
· 공식값·월매출·파생·anomaly·review queue·provenance·배포시각은 기본 메시지에서 제외.
· 직전 발송 스냅샷과 비교해 신규·변경된 외부 추정만 표시(최근 7일 전체 나열 금지).
· 회사별 최대 3건. 변화 없으면 한 줄로 종료. 전체 10줄 내외.
· 증감은 **같은 기관의 직전값**과만 비교(기관이 다르면 비교하지 않음).
· 기준일이 불명확한 값(date_precision=unknown)은 '기준일 미상' 표시.
· 공식값이 새로 발표된 주에만 마지막에 한 줄 추가.
· 같은 주 중복 발송 차단(주차 키). 실제 발송에 성공했을 때만 스냅샷을 갱신한다.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tracker import config
from tracker.database import db
from tracker.metrics import calc
from tracker.notifications import telegram

_KST = ZoneInfo(config.TZ)
DASHBOARD_URL = "https://winner02-spec.github.io/anthropic-runrate-tracker/"
MAX_PER_COMPANY = 3          # 회사별 표시 최대 건수(최신 변화 우선)


def now_kst() -> datetime:
    return datetime.now(timezone.utc).astimezone(_KST)


def week_key(dt: datetime | None = None) -> str:
    d = dt or now_kst()
    y, w, _ = d.isocalendar()
    return f"weekly-digest:{y}-W{w:02d}"


# ── 값 표기 ──────────────────────────────────────────────────────────────────
def _money(v: float | None) -> str:
    return "—" if v is None else f"${v}B"


def _val(p: dict) -> str:
    """qualifier 보존 표기. 약(approximately)은 ~ 로 짧게."""
    s = _money(p.get("value_low_usd_bn"))
    q = p.get("qualifier")
    if q == "approximately":
        return "~" + s
    if q == "over":
        return s + "+"
    return s


def _asof_note(p: dict) -> str:
    return " (기준일 미상)" if (p.get("date_precision") == "unknown") else ""


def _official_when(p: dict) -> str:
    prec, start, end = p.get("date_precision"), p.get("as_of_start"), p.get("as_of_end")
    if prec == "unknown":
        return "기준일 미상"
    if prec == "month_range" and start:
        y, m, _ = start.split("-")
        return f"{y}년 {int(m)}월 중"
    if prec == "year" and start:
        return start[:4]
    return end or start or "—"


# ── 스냅샷(직전 발송 기준선) ─────────────────────────────────────────────────
def _state(conn) -> dict:
    """현재 상태 스냅샷: 회사·기관별 최신 외부추정 + 회사별 최신 공식값."""
    out: dict = {"estimates": {}, "official": {}}
    for c in db.fetchall(conn, "SELECT id, slug, display_name FROM companies ORDER BY id"):
        cid, slug = c["id"], c["slug"]
        rows = [dict(r) for r in db.fetchall(
            conn, "SELECT * FROM runrate_updates WHERE company_id=? AND metric_scope=? "
                  "AND verification_status IN (?,?,?)",
            (cid, config.SCOPE_COMPANY, config.VS_VERIFIED, config.VS_CORROBORATED,
             config.VS_PROVISIONAL))]
        for r in calc.latest_estimates_by_source(rows):
            p = r["point"]
            out["estimates"][f"{slug}|{r['source']}"] = {
                "value": p.get("value_low_usd_bn"), "as_of": p.get("as_of_end"),
                "qualifier": p.get("qualifier"), "date_precision": p.get("date_precision"),
            }
        ann = [r for r in rows if not (r.get("metric_type") == config.MT_MONTHLY_REVENUE
                                       or r.get("is_derived") or r.get("is_estimate"))]
        off = calc.latest_official(ann)
        if off:
            out["official"][slug] = {
                "value": off.get("value_low_usd_bn"), "as_of": off.get("as_of_end"),
                "qualifier": off.get("qualifier"), "metric_type": off.get("metric_type"),
                "date_precision": off.get("date_precision"), "as_of_start": off.get("as_of_start"),
            }
    return out


def last_snapshot(conn) -> dict | None:
    r = db.fetchone(conn, "SELECT payload_json FROM digest_snapshots ORDER BY id DESC LIMIT 1")
    if not r:
        return None
    try:
        return json.loads(r["payload_json"])
    except (ValueError, TypeError):
        return None


def save_snapshot(conn, state: dict, wkey: str, note: str = "") -> int:
    return db.insert(conn, "digest_snapshots", {
        "taken_at": db.now_kst(), "week_key": wkey, "note": note,
        "payload_json": json.dumps(state, ensure_ascii=False)})


def ensure_baseline(conn, wkey: str | None = None) -> bool:
    """최초 운영 기준선. 과거 데이터를 처음 적재한 것을 '이번 주 신규'로 잡지 않도록,
    스냅샷이 하나도 없으면 현재 상태를 기준선으로 저장한다. 저장했으면 True."""
    if last_snapshot(conn) is not None:
        return False
    save_snapshot(conn, _state(conn), wkey or week_key(), note="initial_baseline")
    return True


# ── 변화 계산 ────────────────────────────────────────────────────────────────
def diff_estimates(prev: dict, cur: dict) -> dict[str, list[dict]]:
    """회사별 신규·변경 목록. 같은 기관(source)의 직전값과만 비교한다."""
    changes: dict[str, list[dict]] = {}
    prev_est = (prev or {}).get("estimates", {})
    for key, now in cur.get("estimates", {}).items():
        slug, source = key.split("|", 1)
        before = prev_est.get(key)
        if before is None:
            changes.setdefault(slug, []).append({"source": source, "kind": "new", "now": now})
        elif before.get("value") != now.get("value") or before.get("as_of") != now.get("as_of"):
            if before.get("value") == now.get("value"):
                continue                      # 값 동일(기준일만 갱신) → 보고하지 않음
            changes.setdefault(slug, []).append(
                {"source": source, "kind": "changed", "before": before, "now": now})
    for slug in changes:
        changes[slug].sort(key=lambda c: (c["now"].get("as_of") or ""), reverse=True)
    return changes


def diff_official(prev: dict, cur: dict) -> dict[str, dict]:
    """이번 주에 새로 발표된 공식값(값 또는 기준일이 바뀐 경우)만."""
    prev_off = (prev or {}).get("official", {})
    out = {}
    for slug, now in cur.get("official", {}).items():
        before = prev_off.get(slug)
        if before is None or before.get("value") != now.get("value") or \
                before.get("as_of") != now.get("as_of"):
            out[slug] = now
    return out


# ── 메시지 ───────────────────────────────────────────────────────────────────
def _change_line(c: dict) -> str:
    now = c["now"]
    p = {"value_low_usd_bn": now.get("value"), "qualifier": now.get("qualifier"),
         "date_precision": now.get("date_precision")}
    if c["kind"] == "new":
        return f"· {c['source']}: {_val(p)} 신규{_asof_note(p)}"
    b, n = c["before"].get("value"), now.get("value")
    delta = round((n or 0) - (b or 0), 2)
    pct = round(delta / b * 100, 1) if b else None
    sign = "+" if delta >= 0 else ""
    tail = f" ({sign}${abs(delta) if delta < 0 else delta}B" + \
           (f", {sign}{pct}%)" if pct is not None else ")")
    bp = {"value_low_usd_bn": b, "qualifier": c["before"].get("qualifier"),
          "date_precision": c["before"].get("date_precision")}
    return f"· {c['source']}: {_val(bp)} → {_val(p)}{tail}{_asof_note(p)}"


def build_digest(conn, at: datetime | None = None) -> str:
    prev = last_snapshot(conn)
    cur = _state(conn)
    names = {c["slug"]: c["display_name"]
             for c in db.fetchall(conn, "SELECT slug, display_name FROM companies")}
    lines = ["📊 AI 매출 추정 주간 변화", ""]

    changes = diff_estimates(prev, cur) if prev is not None else {}
    if not changes:
        lines.append("이번 주 신규·변경 추정치 없음.")
    else:
        for slug in [s for s in names if s in changes]:
            lines.append(names[slug])
            for c in changes[slug][:MAX_PER_COMPANY]:
                lines.append(_change_line(c))
            lines.append("")
        if lines[-1] == "":
            lines.pop()

    official_new = diff_official(prev, cur) if prev is not None else {}
    lines += ["", f"🔗 {DASHBOARD_URL}"]
    if official_new:
        parts = []
        for slug, o in official_new.items():
            label = "ARR" if o.get("metric_type") == config.MT_ARR else "Run-rate"
            p = {"value_low_usd_bn": o.get("value"), "qualifier": o.get("qualifier"),
                 "date_precision": o.get("date_precision")}
            parts.append(f"{names.get(slug, slug)} {label} {_val(p)} ({_official_when(o)})")
        lines.append("※ 공식 발표: " + " · ".join(parts))
    return "\n".join(lines)


def send_weekly(conn, dry_run: bool = False, force: bool = False,
                at: datetime | None = None) -> dict:
    """주 1회 게시. 같은 주 재발송은 force=True 일 때만.
    스냅샷은 **실제 발송에 성공했을 때만** 갱신한다(dry-run 은 기준선을 움직이지 않음)."""
    wkey = week_key(at)
    baseline_created = ensure_baseline(conn, wkey) if not dry_run else False
    text = build_digest(conn, at)
    if dry_run:
        return {"status": "dry_run", "week": wkey, "text": text,
                "baseline": last_snapshot(conn) is not None}
    res = telegram.send_keyed(text, wkey, force=force)
    if res.get("status") == "sent":
        save_snapshot(conn, _state(conn), wkey, note="sent")
    return {**res, "week": wkey, "text": text, "baseline_created": baseline_created}
