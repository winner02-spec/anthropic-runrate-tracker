# -*- coding: utf-8 -*-
"""테스트 안전장치 — 테스트가 실제 Telegram 발송을 하지 못하게 강제한다.

.env 에 TELEGRAM_ENABLED=true 가 설정돼 있어도 테스트에서는 항상 dry-run 이어야 한다.
(실 Telegram/Anthropic 미호출 fixture 테스트 원칙)
"""
import pytest

from tracker import config
from tracker.notifications import telegram


@pytest.fixture(autouse=True)
def _never_send_telegram(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "telegram_enabled", lambda: False)
    monkeypatch.setattr(telegram, "_SENT_LOG", tmp_path / "telegram_sent.jsonl")

    def _blocked(*a, **k):   # 혹시라도 HTTP 경로를 타면 즉시 실패시킨다
        raise AssertionError("테스트에서 외부 HTTP 호출 금지(requests.post)")
    monkeypatch.setattr(telegram.requests, "post", _blocked)
