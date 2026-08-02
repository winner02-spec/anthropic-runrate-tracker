# -*- coding: utf-8 -*-
"""주간 다이제스트 — 직전 스냅샷 대비 '외부 추정 변화'만 짧게. 실제 Telegram 미호출."""
from datetime import datetime
from zoneinfo import ZoneInfo

from tracker import config
from tracker.database import db
from tracker.notifications import telegram, weekly

KST = ZoneInfo(config.TZ)
NOW = datetime(2026, 8, 2, 10, 0, tzinfo=KST)


def _conn(tmp_path):
    conn = db.connect(str(tmp_path / "w.sqlite"))
    db.init_db(conn)
    return conn


def _est(conn, slug, value, as_of, source, qualifier="estimate", precision="day"):
    cid = db.company_id_by_slug(conn, slug)
    now = db.now_kst()
    db.insert(conn, "runrate_updates", {
        "company": slug.title(), "company_id": cid, "metric_scope": config.SCOPE_COMPANY,
        "metric_type": config.MT_ARR, "value_low_usd_bn": value, "value_high_usd_bn": None,
        "qualifier": qualifier, "as_of_start": as_of, "as_of_end": as_of, "published_at": as_of,
        "date_precision": precision, "source_name": source, "source_type": "third_party_estimate",
        "source_tier": "C", "is_official": 0, "is_estimate": 1, "is_target": 0,
        "verification_status": config.VS_PROVISIONAL, "status": config.STATUS_CONFIRMED,
        "content_hash": f"{slug}-{source}-{value}-{as_of}", "created_at": now, "updated_at": now})


def _official(conn, slug, value, as_of, qualifier="over"):
    cid = db.company_id_by_slug(conn, slug)
    now = db.now_kst()
    db.insert(conn, "runrate_updates", {
        "company": slug.title(), "company_id": cid, "metric_scope": config.SCOPE_COMPANY,
        "metric_type": config.MT_ARR, "value_low_usd_bn": value, "value_high_usd_bn": None,
        "qualifier": qualifier, "as_of_start": as_of, "as_of_end": as_of, "published_at": as_of,
        "date_precision": "day", "source_name": "Official (x)", "source_type": "official_current",
        "source_tier": "A", "is_official": 1, "is_estimate": 0, "is_target": 0,
        "verification_status": config.VS_CORROBORATED, "status": config.STATUS_CONFIRMED,
        "content_hash": f"off-{slug}-{value}-{as_of}", "created_at": now, "updated_at": now})


def test_first_run_stores_baseline_and_reports_nothing(tmp_path):
    """과거 데이터를 처음 적재한 것을 '이번 주 신규'로 잡지 않는다."""
    conn = _conn(tmp_path)
    _est(conn, "openai", 40.3, "2026-07-09", "TickerTrends (OpenAI ARR 추정)")
    assert weekly.ensure_baseline(conn, weekly.week_key(NOW)) is True
    text = weekly.build_digest(conn, at=NOW)
    assert text.splitlines()[0] == "📊 AI 매출 추정 주간 변화"
    assert "이번 주 신규·변경 추정치 없음." in text
    assert weekly.DASHBOARD_URL in text
    assert len(text.splitlines()) <= 10
    assert weekly.ensure_baseline(conn) is False        # 기준선은 한 번만


def test_only_changes_since_last_snapshot_same_source_only(tmp_path):
    conn = _conn(tmp_path)
    _est(conn, "openai", 40.3, "2026-07-09", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, "anthropic", 71.9, "2026-07-09", "TickerTrends (외부 추정)")
    weekly.ensure_baseline(conn, weekly.week_key(NOW))          # 기준선 = 여기까지

    _est(conn, "openai", 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")
    _est(conn, "anthropic", 74.3, "2026-07-22", "TickerTrends (외부 추정)")
    _est(conn, "anthropic", 71.0, "2026-07-28", "Funda (재인용, 원자료 미확인)",
         qualifier="approximately", precision="unknown")
    text = weekly.build_digest(conn, at=NOW)

    assert "· TickerTrends: $40.3B → $42.6B (+$2.3B, +5.7%)" in text
    assert "· TickerTrends: $71.9B → $74.3B (+$2.4B, +3.3%)" in text
    assert "· Funda: ~$71.0B 신규 (기준일 미상)" in text
    # 전체 현황(공식·월매출·파생·anomaly·배포)은 기본 메시지에서 제외
    for banned in ("공식 ARR:", "파생", "이상 탐지", "검토 대기", "배포", "provenance"):
        assert banned not in text
    # 기관이 다른 값끼리 증감률을 만들지 않는다(Funda 는 '신규'로만 표기)
    assert "Funda: $" not in text


def test_max_three_per_company(tmp_path):
    conn = _conn(tmp_path)
    weekly.ensure_baseline(conn, weekly.week_key(NOW))
    for i, src in enumerate(["A (x)", "B (x)", "C (x)", "D (x)"]):
        _est(conn, "openai", 10 + i, f"2026-07-0{i+1}", src)
    text = weekly.build_digest(conn, at=NOW)
    assert sum(1 for l in text.splitlines() if l.startswith("· ")) == weekly.MAX_PER_COMPANY


def test_official_line_only_when_new_official(tmp_path):
    conn = _conn(tmp_path)
    _official(conn, "anthropic", 30, "2026-04-06")
    weekly.ensure_baseline(conn, weekly.week_key(NOW))
    assert "공식 발표" not in weekly.build_digest(conn, at=NOW)

    _official(conn, "anthropic", 47, "2026-05-15")
    text = weekly.build_digest(conn, at=NOW)
    assert text.splitlines()[-1].startswith("※ 공식 발표: Anthropic ARR $47.0B+")


def test_week_dedup_and_snapshot_only_advances_on_send(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    _est(conn, "openai", 40.3, "2026-07-09", "TickerTrends (OpenAI ARR 추정)")
    weekly.ensure_baseline(conn, weekly.week_key(NOW))
    _est(conn, "openai", 42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)")

    # dry-run 은 기준선을 움직이지 않는다(같은 변화가 실제 발송 때 또 보여야 함)
    n_before = db.fetchone(conn, "SELECT COUNT(*) FROM digest_snapshots")[0]
    assert "→ $42.6B" in weekly.send_weekly(conn, dry_run=True, at=NOW)["text"]
    assert db.fetchone(conn, "SELECT COUNT(*) FROM digest_snapshots")[0] == n_before

    monkeypatch.setattr(telegram, "send_keyed", lambda text, key, force=False: {"status": "sent"})
    sent = weekly.send_weekly(conn, at=NOW)
    assert sent["status"] == "sent" and sent["week"] == "weekly-digest:2026-W31"
    assert db.fetchone(conn, "SELECT COUNT(*) FROM digest_snapshots")[0] == n_before + 1
    # 발송 후에는 같은 변화가 다시 보고되지 않는다
    assert "이번 주 신규·변경 추정치 없음." in weekly.build_digest(conn, at=NOW)


def test_same_week_resend_blocked_without_force(tmp_path):
    conn = _conn(tmp_path)
    weekly.ensure_baseline(conn, weekly.week_key(NOW))
    first = weekly.send_weekly(conn, at=NOW)       # conftest 가 dry-run 강제 → 발송은 안 됨
    second = weekly.send_weekly(conn, at=NOW)
    assert first["status"] == "dry_run"
    assert second["status"] == "duplicate_skipped"
    assert weekly.send_weekly(conn, at=NOW, force=True)["status"] == "dry_run"
