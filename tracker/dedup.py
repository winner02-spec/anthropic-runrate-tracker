# -*- coding: utf-8 -*-
"""중복 판정: 기사 단위(content_hash) + 데이터포인트 단위(semantic_key).

· content_hash: 동일 기사/동일 추출 재수집 방지.
· semantic_key: 같은 공식 발표를 여러 매체가 재인용해도 새 데이터포인트로 중복 추가하지 않기 위함
  (같은 값·기준시점·공식여부면 동일 포인트로 간주).
"""
from __future__ import annotations
import hashlib
import re
from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url.strip())
    except (ValueError, AttributeError):
        return url.strip().lower()
    host = re.sub(r"^www\.", "", (p.netloc or "").lower())
    path = re.sub(r"/+$", "", p.path or "")
    return urlunparse(("https", host, path, "", "", ""))  # query/fragment 제거


def normalize_title(title: str) -> str:
    t = (title or "").lower()
    t = re.sub(r"[^a-z0-9가-힣 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _sig(*parts) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def content_hash(url: str, title: str, published_at, value_low, value_high, qualifier,
                 evidence_text: str = "") -> str:
    """기사+추출 단위 고유값(재수집/재추출 중복 방지). 회사 스코프는 scoped_hash 로 감싼다."""
    return _sig(canonical_url(url), normalize_title(title), published_at,
                value_low, value_high, qualifier, normalize_title(evidence_text)[:120])


def scoped_hash(slug: str, base_hash: str) -> str:
    """회사 스코프 래핑: 서로 다른 회사의 동일 기사/숫자가 같은 hash 로 충돌하지 않도록
    기존 base content_hash 를 slug 로 한 번 더 감싼다(원자료 재구성 불필요 → migration 안전)."""
    return _sig(slug or "", base_hash)


def company_content_hash(slug: str, url: str, title: str, published_at, value_low,
                         value_high, qualifier, evidence_text: str = "") -> str:
    """회사 스코프 content_hash(모든 write 경로 공용)."""
    return scoped_hash(slug, content_hash(url, title, published_at, value_low,
                                          value_high, qualifier, evidence_text))


def semantic_key(slug, metric_scope, metric_type, value_low, value_high, qualifier,
                 as_of_end, is_official, is_estimate, is_target) -> str:
    """데이터포인트 동일성(같은 발표 재인용 중복 방지). 회사(slug)별로 분리."""
    return _sig(slug or "", metric_scope, metric_type, value_low, value_high, qualifier,
                as_of_end, int(bool(is_official)), int(bool(is_estimate)), int(bool(is_target)))
