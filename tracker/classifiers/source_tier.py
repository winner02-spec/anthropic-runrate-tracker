# -*- coding: utf-8 -*-
"""출처 URL → 등급(A/B/C/D) 분류. sources.yml 의 source_tiers 매핑 사용."""
from __future__ import annotations
import re
from urllib.parse import urlparse
import yaml

from tracker import config

_cache: dict | None = None


def _tiers() -> dict:
    global _cache
    if _cache is None:
        data = yaml.safe_load(config.SOURCES_YML.read_text(encoding="utf-8")) or {}
        _cache = data.get("source_tiers", {})
    return _cache


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except (ValueError, AttributeError):
        return ""
    return re.sub(r"^www\.", "", host)


def classify_tier(url: str) -> str:
    """알려진 도메인 → A/B/C. 그 외/불명확 → D(검토큐)."""
    host = domain_of(url)
    if not host:
        return "D"
    tiers = _tiers()
    for tier in ("A", "B", "C", "D"):
        for dom in tiers.get(tier, []) or []:
            d = re.sub(r"^www\.", "", str(dom).lower())
            if host == d or host.endswith("." + d):
                return tier
    return "D"
