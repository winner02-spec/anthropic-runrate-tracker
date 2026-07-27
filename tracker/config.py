# -*- coding: utf-8 -*-
"""전역 설정·경로·상수. 비밀값은 .env 에서만 로드(커밋 금지)."""
from __future__ import annotations
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
DB_PATH = DATABASE_DIR / "runrate.sqlite"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
SEEDS_DIR = BASE_DIR / "data" / "seeds"
SOURCES_YML = CONFIG_DIR / "sources.yml"
# 배포 프론트가 읽는 정적 JSON(비밀 없음)
DASHBOARD_JSON = BASE_DIR / "frontend" / "public" / "data" / "dashboard.json"

TZ = "Asia/Seoul"
BASE_CURRENCY = "USD"
BASE_UNIT = "billion"  # 금액 표준 단위: USD billion

# ── qualifier(숫자 표현) ──
QUALIFIERS = ("exact", "approximately", "over", "range", "target", "estimate", "reported")

# ── 상태 ──
STATUS_CONFIRMED = "confirmed"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_REJECTED = "rejected"
STATUS_SUPERSEDED = "superseded"

# ── metric_scope / metric_type ──
SCOPE_COMPANY = "company"       # 전사 Anthropic
SCOPE_PRODUCT = "product"       # Claude Code 등 제품별
METRIC_RUNRATE = "revenue_run_rate"
METRIC_VALUATION = "valuation"


def _load_env(path: Path | None = None) -> dict:
    d: dict[str, str] = {}
    p = path or (BASE_DIR / ".env")
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip().strip('"').strip("'")
    return d


_ENV = _load_env()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key) or _ENV.get(key, default)


def telegram_enabled() -> bool:
    return env("TELEGRAM_ENABLED", "false").lower() == "true"


def ensure_dirs() -> None:
    for d in (DATABASE_DIR, LOGS_DIR, DASHBOARD_JSON.parent):
        d.mkdir(parents=True, exist_ok=True)
