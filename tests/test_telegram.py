# -*- coding: utf-8 -*-
from tracker.notifications import telegram


def test_dry_run_and_dedup(tmp_path, monkeypatch):
    monkeypatch.setattr(telegram, "_SENT_LOG", tmp_path / "sent.jsonl")
    # 키 없음 → dry-run
    monkeypatch.setattr(telegram.config, "telegram_enabled", lambda: False)
    r1 = telegram.send("🟢 test message")
    assert r1["status"] == "dry_run"
    # 동일 내용 재발송 → 중복 skip
    r2 = telegram.send("🟢 test message")
    assert r2["status"] == "duplicate_skipped"


def test_official_template_contains_values():
    txt = telegram.format_official(
        {"value_low_usd_bn": 47, "as_of_end": "2026-05-15", "published_at": "2026-05-29",
         "source_name": "Anthropic"},
        {"value_low_usd_bn": 14})
    assert "$47.00B" in txt and "$14.00B" in txt
    assert "공식 Run-rate" in txt
