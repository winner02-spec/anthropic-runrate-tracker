# -*- coding: utf-8 -*-
import yaml
from tracker.database import db
from tracker import backfill, config
from tracker.classifiers import feedback
from tracker.export import dashboard

OFFICIAL = {"group": "official", "metric_scope": "company", "value_low_usd_bn": 14,
            "qualifier": "exact", "as_of_start": "2026-02-12", "as_of_end": "2026-02-12",
            "date_precision": "day", "published_at": "2026-02-12", "source_name": "Anthropic",
            "source_url": "https://www.anthropic.com/news/x", "source_type": "official_current",
            "is_official": 1, "verification_status": "verified", "evidence_text": "run-rate is $14B"}
ESTIMATE = {"group": "estimates_tickertrends", "metric_scope": "company", "value_low_usd_bn": 54.6,
            "qualifier": "estimate", "as_of_start": "2026-05-21", "as_of_end": "2026-05-21",
            "source_name": "TickerTrends", "source_type": "third_party_estimate",
            "is_estimate": 1, "verification_status": "provisional",
            "source_note": "사용자 제공 TickerTrends 이미지", "evidence_note": "이미지에서 $54.6B 식별"}


def _conn(tmp_path, points):
    (tmp_path / "backfill_sources.yml").write_text(
        yaml.safe_dump({"points": points}), encoding="utf-8")
    config.BACKFILL_SOURCES_YML = tmp_path / "backfill_sources.yml"
    conn = db.connect(str(tmp_path / "t.sqlite"))
    db.init_db(conn)
    return conn


def test_backfill_rerun_no_duplicate(tmp_path):
    conn = _conn(tmp_path, [OFFICIAL])
    r1 = backfill.run_backfill(conn)
    r2 = backfill.run_backfill(conn)
    assert r1["added"] == 1
    assert r2["added"] == 0 and r2["duplicates"] == 1   # 재실행 중복 0


def test_estimates_image_only_provisional(tmp_path, monkeypatch):
    # auto_approve=false(기본) → 이미지 기반 추정은 verified/corroborated 로 못 올라가고 provisional.
    # provisional 은 공식선엔 절대 미포함, 외부추정(estimated) 선에는 '원문 미확인'으로 표시.
    monkeypatch.setattr(config, "settings", lambda: {"estimates": {"auto_approve": False},
                                                     "llm": {}, "schedule": {}, "collect": {}})
    conn = _conn(tmp_path, [ESTIMATE])
    backfill.run_backfill(conn)
    row = db.fetchone(conn, "SELECT verification_status, is_estimate FROM runrate_updates WHERE value_low_usd_bn=54.6")
    assert row["verification_status"] == "provisional" and row["is_estimate"] == 1
    payload = dashboard.build_payload(conn)
    assert payload["series"]["official"] == []                    # 공식선 미포함
    assert len(payload["series"]["estimated"]) == 1               # 외부추정선에는 표시
    assert payload["series"]["estimated"][0]["verification_status"] == "provisional"


def test_feedback_record_and_reuse(tmp_path):
    conn = _conn(tmp_path, [OFFICIAL])
    feedback.record(conn, source_domain="badnews.example",
                    original_classification="official_current", final_classification="reject",
                    original_metric_scope="company", final_metric_scope="company",
                    approval_action="reject")
    assert feedback.domain_should_review(conn, "badnews.example") is True
    assert feedback.domain_should_review(conn, "clean.example") is False


def test_feedback_does_not_promote_to_official(tmp_path):
    # 피드백만으로 외부추정을 공식으로 승격하지 않음(플래그 불변)
    conn = _conn(tmp_path, [ESTIMATE])
    backfill.run_backfill(conn)
    feedback.record(conn, source_domain="tickertrends.com",
                    original_classification="third_party_estimate",
                    final_classification="third_party_estimate", approval_action="approve")
    row = db.fetchone(conn, "SELECT is_official FROM runrate_updates WHERE value_low_usd_bn=54.6")
    assert row["is_official"] == 0
