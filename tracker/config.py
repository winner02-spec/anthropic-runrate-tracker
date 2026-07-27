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
QUALIFIERS = ("exact", "approximately", "approaching", "over", "range", "target",
              "estimate", "reported")

# ── source_type 분류 체계 ──
ST_OFFICIAL_CURRENT = "official_current"           # 공식 발표 당시 '현재값'
ST_OFFICIAL_RETROSPECTIVE = "official_retrospective"  # 공식자료가 회고한 과거값
ST_REPORTED = "reported"                            # 주요 매체 보도(자체)
ST_REPORTED_COMPANY = "reported_company_statement"  # 매체가 회사 공식발언 재인용
ST_THIRD_PARTY_ESTIMATE = "third_party_estimate"    # TickerTrends/Yipit/Sacra 등 외부추정
ST_TARGET = "target"                                # 목표치
SOURCE_TYPES = (ST_OFFICIAL_CURRENT, ST_OFFICIAL_RETROSPECTIVE, ST_REPORTED,
                ST_REPORTED_COMPANY, ST_THIRD_PARTY_ESTIMATE, ST_TARGET)

# ── 계층형 검증 상태 ──
VS_VERIFIED = "verified"            # 공식/직접 기사 URL + evidence + published → 정상 표시
VS_CORROBORATED = "corroborated"    # 직접 원문 어려우나 복수 매체/회사 인용 교차확인 → '간접 확인'
VS_PROVISIONAL = "provisional"      # 이미지/메모로 숫자 확인, URL 미확인 → 외부추정선 '원문 미확인'
VS_NEEDS_REVIEW = "needs_review"    # 불명확 → 공개 JSON 제외, review queue
VERIFICATION_STATUSES = (VS_VERIFIED, VS_CORROBORATED, VS_PROVISIONAL, VS_NEEDS_REVIEW)
# 대시보드에 표시되는 검증상태(needs_review 제외)
VS_SHOWN = (VS_VERIFIED, VS_CORROBORATED, VS_PROVISIONAL)

SETTINGS_YML = CONFIG_DIR / "settings.yml"
BACKFILL_SOURCES_YML = CONFIG_DIR / "backfill_sources.yml"


def settings() -> dict:
    """앱 설정(config/settings.yml). 파일 없으면 안전 기본값."""
    import yaml
    default = {
        "estimates": {"auto_approve": False},
        "llm": {"enabled": False, "only_on_new_candidates": True, "batch_candidates": True},
        "schedule": {"daily_discovery": "08:30", "weekly_backfill": "Sun 09:00",
                     "health_check": "09:30"},
        "collect": {"recent_days": 7},
    }
    try:
        loaded = yaml.safe_load(SETTINGS_YML.read_text(encoding="utf-8")) or {}
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(default.get(k), dict):
                default[k].update(v)
            else:
                default[k] = v
    except Exception:
        pass
    return default

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
