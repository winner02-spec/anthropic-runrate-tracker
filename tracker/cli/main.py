# -*- coding: utf-8 -*-
"""검토·운영 CLI.  실행:  python -m tracker <command>

명령: init · seed · collect · review · approve <id> · reject <id> ·
      add-url <url> · add-manual · export · status
"""
from __future__ import annotations
import argparse
import json
import sys

from tracker import config
from tracker.database import db
from tracker import ingest
from tracker.collectors import seed as seedmod
from tracker.export import dashboard
from tracker.notifications import telegram


def _conn():
    conn = db.connect()
    db.init_db(conn)
    return conn


def cmd_init(args) -> int:
    conn = _conn()
    print(f"[OK] DB 초기화 → {config.DB_PATH}")
    conn.close()
    return 0


def cmd_seed(args) -> int:
    conn = _conn()
    res = seedmod.load_all_seeds(conn)
    conn.close()
    print("[OK] seed 병합(중복 제외 신규):", json.dumps(res, ensure_ascii=False))
    return 0


def cmd_collect(args) -> int:
    conn = _conn()
    res = ingest.run_collect(conn, mode=args.mode, dry_run=args.dry_run,
                             company=getattr(args, "company", None))
    print(f"[collect mode={args.mode}]", json.dumps({k: res[k] for k in
          ("docs_found", "new_candidates", "confirmed", "duplicates", "skipped_cached",
           "api_calls", "est_tokens")}, ensure_ascii=False))
    if res["errors"]:
        print("  경고:", "; ".join(res["errors"][:5]))
    if not args.dry_run:
        _notify_new(conn)
        ch = dashboard.write_if_changed(conn)   # 변경 시에만 export
        print("  → dashboard.json 갱신" if ch["written"] else "  → 데이터 변경 없음: export 생략")
    conn.close()
    return 0


def cmd_backfill(args) -> int:
    from tracker import backfill
    conn = _conn()
    res = backfill.run_backfill(conn, date_from=getattr(args, "from"), date_to=args.to,
                                source_filter=args.source, dry_run=args.dry_run)
    print(f"[backfill {'DRY' if args.dry_run else 'MERGE'}]", json.dumps(res, ensure_ascii=False))
    if not args.dry_run and res["added"]:
        ch = dashboard.write_if_changed(conn)
        print("  → dashboard.json 갱신" if ch["written"] else "  → 변경 없음")
    conn.close()
    return 0


def cmd_verify_history(args) -> int:
    from tracker import verify
    conn = _conn()
    res = verify.verify_history(conn, record=args.record)
    print(f"verify-history · 공식 포인트 {res['official_points']} · 총 이슈 {res['total_issues']}")
    for typ, items in res["issues"].items():
        if items:
            print(f"  [{typ}] {len(items)}건")
            for it in items[:5]:
                print("     -", it)
    if res["total_issues"] == 0:
        print("  ✅ 이상 없음")
    conn.close()
    return 0


def _notify_new(conn) -> None:
    # 신규 확정 공식/추정 + 검토 후보 알림(중복 방지, 기본 dry-run)
    offs = db.fetchall(conn, "SELECT * FROM runrate_updates WHERE status=? AND is_official=1 "
                             "ORDER BY as_of_end ASC", (config.STATUS_CONFIRMED,))
    if offs:
        rows = [dict(r) for r in offs]
        prev = rows[-2] if len(rows) >= 2 else None
        telegram.send(telegram.format_official(rows[-1], prev))
    for rq in db.fetchall(conn, "SELECT * FROM review_queue WHERE status='pending' "
                                "ORDER BY id DESC LIMIT 5"):
        telegram.send(telegram.format_review(dict(rq)))


def cmd_review(args) -> int:
    conn = _conn()
    rows = db.fetchall(conn, "SELECT * FROM review_queue WHERE status='pending' ORDER BY id ASC")
    if not rows:
        print("검토 대기 후보 없음.")
        return 0
    for r in rows:
        d = dict(r)
        print("─" * 60)
        print(f"[검토 ID {d['id']}] {d.get('found_expression')}  · {d.get('classification')} "
              f"· {d.get('source_tier')}")
        print(f"  출처: {d.get('source_name')} {d.get('source_url')}")
        print(f"  발표일 {d.get('published_at')} · 기준 {d.get('as_of_start')}~{d.get('as_of_end')} "
              f"· 신뢰도 {d.get('confidence_score')}")
        print(f"  근거: {d.get('evidence_text')}")
        print(f"  처리: python -m tracker approve {d['id']}  |  reject {d['id']}")
    conn.close()
    return 0


def cmd_approve(args) -> int:
    conn = _conn()
    rq = db.fetchone(conn, "SELECT * FROM review_queue WHERE id=?", (args.id,))
    if not rq:
        print(f"검토 ID {args.id} 없음."); return 1
    rq = dict(rq)
    now = db.now_kst()
    rr = None
    if rq.get("runrate_update_id"):
        rr = db.fetchone(conn, "SELECT * FROM runrate_updates WHERE id=?", (rq["runrate_update_id"],))
        conn.execute("UPDATE runrate_updates SET status=?, updated_at=? WHERE id=?",
                     (config.STATUS_CONFIRMED, now, rq["runrate_update_id"]))
    conn.execute("UPDATE review_queue SET status='approved' WHERE id=?", (args.id,))
    conn.commit()
    _record_feedback(conn, rq, rr, action="approve")
    dashboard.write_dashboard(conn)
    print(f"[OK] 승인 · dashboard 갱신 (검토 ID {args.id})")
    conn.close()
    return 0


def _record_feedback(conn, rq: dict, rr, action: str) -> None:
    from tracker.classifiers import feedback
    from tracker.classifiers.source_tier import domain_of
    d = dict(rr) if rr else {}
    feedback.record(
        conn, candidate_id=rq.get("runrate_update_id"),
        source_domain=domain_of(rq.get("source_url") or d.get("source_url") or ""),
        original_classification=rq.get("classification") or d.get("source_type") or "",
        final_classification=d.get("source_type") or "",
        original_metric_scope=d.get("metric_scope") or "",
        final_metric_scope=d.get("metric_scope") or "",
        original_qualifier=d.get("qualifier") or "",
        final_qualifier=d.get("qualifier") or "",
        approval_action=action,
        evidence_pattern=(d.get("evidence_text") or rq.get("evidence_text") or "")[:120])


def cmd_reject(args) -> int:
    conn = _conn()
    rq = db.fetchone(conn, "SELECT * FROM review_queue WHERE id=?", (args.id,))
    if not rq:
        print(f"검토 ID {args.id} 없음."); return 1
    rq = dict(rq)
    rr = None
    if rq.get("runrate_update_id"):
        rr = db.fetchone(conn, "SELECT * FROM runrate_updates WHERE id=?", (rq["runrate_update_id"],))
        conn.execute("UPDATE runrate_updates SET status=? WHERE id=?",
                     (config.STATUS_REJECTED, rq["runrate_update_id"]))
    conn.execute("UPDATE review_queue SET status='rejected' WHERE id=?", (args.id,))
    conn.commit()
    _record_feedback(conn, rq, rr, action="reject")
    print(f"[OK] 거절 · 피드백 저장 (검토 ID {args.id})")
    conn.close()
    return 0


def cmd_add_url(args) -> int:
    path = config.CONFIG_DIR / "manual_urls.txt"
    with open(path, "a", encoding="utf-8") as f:
        f.write(args.url.strip() + "\n")
    print(f"[OK] 수동 URL 추가 → {path}")
    return 0


def cmd_add_manual(args) -> int:
    """검증된 데이터포인트 수동 입력. 원문·근거 없으면 needs_review 로.

    플래그로 지정(권장): --value --source-url --evidence --as-of --published-at --official
    미지정 항목은 터미널에서 프롬프트로 입력받는다.
    """
    conn = _conn()
    from tracker import dedup
    from tracker.classifiers.source_tier import classify_tier

    def ask(label, cur):
        if cur is not None:
            return cur
        v = input(f"{label}: ").strip()
        return v or None

    raw_value = args.value if args.value is not None else ask("value_low_usd_bn", None)
    value = float(raw_value) if raw_value not in (None, "") else None
    source_url = ask("source_url", args.source_url)
    published = ask("published_at(YYYY-MM-DD)", args.published_at)
    as_of = ask("as_of_end(YYYY-MM-DD)", args.as_of)
    evidence = ask("evidence_text", args.evidence)
    is_official = 1 if args.official else 0
    tier = classify_tier(source_url or "")
    status = (config.STATUS_CONFIRMED if (is_official and source_url and evidence)
              else config.STATUS_NEEDS_REVIEW)
    now = db.now_kst()
    slug = (getattr(args, "company", None) or "anthropic").strip().lower()
    comp = config.companies_config().get(slug, {})
    cid = db.ensure_company(conn, slug, comp.get("display_name") or slug.title(),
                            comp.get("official_domain"))
    ch = dedup.company_content_hash(slug, source_url or "", "manual", published, value, None,
                                    args.qualifier or "exact", evidence or "")
    row = {"company": comp.get("display_name") or slug.title(), "company_id": cid,
           "metric_scope": config.SCOPE_COMPANY,
           "metric_type": config.METRIC_RUNRATE, "value_low_usd_bn": value,
           "value_high_usd_bn": None, "original_value": args.original or f"${value}B",
           "original_currency": "USD", "original_unit": "billion",
           "qualifier": args.qualifier or "exact", "as_of_start": as_of, "as_of_end": as_of,
           "published_at": published, "source_name": args.source_name or "manual",
           "source_url": source_url, "source_tier": tier,
           "source_type": "official" if is_official else "reported",
           "status": status, "confidence_score": 0.8 if is_official else 0.5,
           "evidence_text": evidence, "is_official": is_official, "is_estimate": 0,
           "is_target": 1 if args.qualifier == "target" else 0,
           "content_hash": ch, "created_at": now, "updated_at": now}
    rid = db.insert(conn, "runrate_updates", row)
    if rid is None:
        print("이미 존재(중복) — 미입력.")
    else:
        print(f"[OK] 수동 입력 id={rid} status={status}")
        dashboard.write_dashboard(conn)
    conn.close()
    return 0


def cmd_health(args) -> int:
    from tracker import health
    conn = _conn()
    res = health.run_health(conn)
    print("health check:")
    for k, v in res.items():
        print(f"  {k}: {v}")
    conn.close()
    return 0


def cmd_export(args) -> int:
    conn = _conn()
    out = dashboard.write_dashboard(conn)
    print(f"[OK] dashboard.json 생성 → {out}")
    conn.close()
    return 0


def cmd_status(args) -> int:
    conn = _conn()

    def c(sql, a=()):
        r = db.fetchone(conn, sql, a)
        return r[0] if r else 0

    conf = (config.STATUS_CONFIRMED,)
    last = db.fetchone(conn, "SELECT finished_at FROM ingestion_runs ORDER BY id DESC LIMIT 1")
    print("Frontier AI Revenue Tracker — 상태")
    print(f"  DB: {config.DB_PATH}")
    for co in db.fetchall(conn, "SELECT id, slug, display_name FROM companies ORDER BY id"):
        cid = co["id"]

        def cc(sql):
            r = db.fetchone(conn, sql, (cid,) + conf)
            return r[0] if r else 0
        n_official = cc("SELECT COUNT(*) FROM runrate_updates WHERE company_id=? AND status=? AND is_official=1 AND is_derived=0")
        n_derived = c("SELECT COUNT(*) FROM runrate_updates WHERE company_id=? AND status=? AND is_derived=1", (cid,) + conf)
        n_estimate = cc("SELECT COUNT(*) FROM runrate_updates WHERE company_id=? AND status=? AND is_estimate=1")
        n_target = cc("SELECT COUNT(*) FROM runrate_updates WHERE company_id=? AND status=? AND is_target=1")
        n_val = c("SELECT COUNT(*) FROM valuation_updates WHERE company_id=?", (cid,))
        n_prod = c("SELECT COUNT(*) FROM product_metrics WHERE company_id=?", (cid,))
        n_evt = c("SELECT COUNT(*) FROM source_events WHERE company_id=?", (cid,))
        n_review = c("SELECT COUNT(*) FROM review_queue WHERE company_id=? AND status='pending'", (cid,))
        print(f"  [{co['display_name']}] 공식 {n_official} · 파생 {n_derived} · 추정 {n_estimate} · 목표 {n_target} · "
              f"밸류 {n_val} · 제품 {n_prod} · 이벤트 {n_evt} · 검토대기 {n_review}")
    print(f"  마지막 수집: {last[0] if last else '—'}")
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracker", description="Anthropic Revenue Run-rate Tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("seed").set_defaults(func=cmd_seed)
    c = sub.add_parser("collect")
    c.add_argument("--mode", choices=["daily", "discovery"], default="daily")
    c.add_argument("--company", default=None, help="slug(anthropic|openai) 또는 all(기본)")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=cmd_collect)
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="from")
    b.add_argument("--to", default="today")
    b.add_argument("--source", choices=["official", "reuters", "estimates"])
    b.add_argument("--dry-run", action="store_true")
    b.set_defaults(func=cmd_backfill)
    vh = sub.add_parser("verify-history")
    vh.add_argument("--record", action="store_true")
    vh.set_defaults(func=cmd_verify_history)
    sub.add_parser("review").set_defaults(func=cmd_review)
    a = sub.add_parser("approve"); a.add_argument("id", type=int); a.set_defaults(func=cmd_approve)
    r = sub.add_parser("reject"); r.add_argument("id", type=int); r.set_defaults(func=cmd_reject)
    u = sub.add_parser("add-url"); u.add_argument("url"); u.set_defaults(func=cmd_add_url)
    m = sub.add_parser("add-manual")
    for opt in ("--value", "--as-of", "--published-at", "--source-url", "--source-name",
                "--evidence", "--qualifier", "--original", "--company"):
        m.add_argument(opt)
    m.add_argument("--official", action="store_true")
    m.set_defaults(func=cmd_add_manual)
    sub.add_parser("export").set_defaults(func=cmd_export)
    sub.add_parser("health").set_defaults(func=cmd_health)
    sub.add_parser("status").set_defaults(func=cmd_status)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
