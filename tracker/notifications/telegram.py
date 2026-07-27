# -*- coding: utf-8 -*-
"""Telegram 알림. 키 없거나 TELEGRAM_ENABLED=false 면 dry-run(콘솔/로그)만.
같은 내용 중복 알림 금지(logs/telegram_sent.jsonl 로 dedup)."""
from __future__ import annotations
import json
import hashlib
import requests

from tracker import config

_SENT_LOG = config.LOGS_DIR / "telegram_sent.jsonl"


def _money(v) -> str:
    return "—" if v is None else f"${v:.2f}B"


def format_official(new: dict, prev: dict | None) -> str:
    prev_v = prev.get("value_low_usd_bn") if prev else None
    new_v = new.get("value_low_usd_bn")
    delta = (round(new_v - prev_v, 3) if (new_v is not None and prev_v is not None) else None)
    return (
        "🟢 Anthropic 공식 Run-rate 업데이트\n\n"
        f"· 이전 공식값: {_money(prev_v)}\n"
        f"· 신규 공식값: {_money(new_v)}\n"
        f"· 변화: {('+' if (delta or 0) >= 0 else '')}{delta if delta is not None else '—'}B\n"
        f"· 기준일: {new.get('as_of_end') or '—'}\n"
        f"· 발표일: {new.get('published_at') or '—'}\n"
        f"· 출처: {new.get('source_name') or '—'}"
    )


def format_estimate(new: dict, last_official: dict | None) -> str:
    ov = last_official.get("value_low_usd_bn") if last_official else None
    ev = new.get("value_low_usd_bn")
    gap = (round(ev - ov, 3) if (ev is not None and ov is not None) else None)
    return (
        "🟠 Anthropic Run-rate 신규 추정치\n\n"
        f"· 추정값: {_money(ev)}\n"
        f"· 마지막 공식값: {_money(ov)}\n"
        f"· 차이: {gap if gap is not None else '—'}B\n"
        f"· 기준일: {new.get('as_of_end') or '—'}\n"
        f"· 출처 등급: {new.get('source_tier') or '—'}\n"
        "· 상태: 공식 확인 전\n\n※ 공식 시계열에는 미반영"
    )


def format_review(candidate: dict) -> str:
    return (
        "⚪️ Anthropic 신규 숫자 후보\n\n"
        f"· 발견 표현: {candidate.get('found_expression') or '—'}\n"
        f"· 분류 추정: {candidate.get('classification') or '—'}\n"
        f"· 출처: {candidate.get('source_name') or '—'} ({candidate.get('source_tier') or '—'})\n"
        f"· 신뢰도: {candidate.get('confidence_score') or 0}\n"
        f"· 검토 ID: {candidate.get('id')}"
    )


def _dedup_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _already_sent(key: str) -> bool:
    if not _SENT_LOG.exists():
        return False
    for line in _SENT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("key") == key:
                return True
        except json.JSONDecodeError:
            continue
    return False


def _record_sent(key: str, dry: bool) -> None:
    config.ensure_dirs()
    with open(_SENT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "dry_run": dry}, ensure_ascii=False) + "\n")


def send(text: str, force: bool = False) -> dict:
    """중복이면 skip. 키 없거나 비활성이면 dry-run. 반환: 상태 dict."""
    key = _dedup_key(text)
    if not force and _already_sent(key):
        return {"status": "duplicate_skipped"}

    token = config.env("TELEGRAM_BOT_TOKEN")
    chat = config.env("TELEGRAM_CHAT_ID")
    enabled = config.telegram_enabled() and token and chat
    if not enabled:
        print("[TELEGRAM dry-run]\n" + text + "\n")
        _record_sent(key, dry=True)
        return {"status": "dry_run"}

    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                      timeout=20)
    ok = r.json().get("ok", False)
    if ok:
        _record_sent(key, dry=False)
    return {"status": "sent" if ok else "failed", "resp": r.json()}
