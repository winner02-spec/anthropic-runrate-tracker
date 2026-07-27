# -*- coding: utf-8 -*-
"""수집기 공용: Document 모델 + HTTP + HTML 텍스트 추출.

전문 저장 금지 원칙: 본문은 분석용으로만 쓰고, 저장은 제목·날짜·URL·근거문장·구조화 숫자만.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import requests
from bs4 import BeautifulSoup

DEFAULT_UA = "anthropic-runrate-tracker/0.1 (research)"


@dataclass
class Document:
    title: str
    url: str
    text: str                  # 분석용(저장 안 함)
    published_at: str | None
    source_name: str
    tier: str


def http_get(url: str, timeout: int = 25, ua: str = DEFAULT_UA) -> requests.Response:
    return requests.get(url, headers={"User-Agent": ua}, timeout=timeout)


def conditional_get(conn, url: str, timeout: int = 25, ua: str = DEFAULT_UA):
    """fetch_cache 기반 조건부 GET. 내용이 안 바뀌었으면 (None, True) 반환(재분석 스킵).
    바뀌었으면 (response, False) + 캐시 갱신. → 토큰/비용 절감."""
    import hashlib
    from tracker.database import db
    row = db.fetchone(conn, "SELECT etag, last_modified, content_hash FROM fetch_cache WHERE url=?", (url,))
    headers = {"User-Agent": ua}
    if row:
        if row["etag"]:
            headers["If-None-Match"] = row["etag"]
        if row["last_modified"]:
            headers["If-Modified-Since"] = row["last_modified"]
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except Exception:
        return None, False
    if r.status_code == 304:
        return None, True   # 서버가 '안 바뀜' 확인
    chash = hashlib.sha256(r.content or b"").hexdigest()[:32]
    same = bool(row and row["content_hash"] == chash)
    conn.execute(
        "INSERT INTO fetch_cache(url, etag, last_modified, content_hash, last_fetched_at) "
        "VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET etag=excluded.etag, "
        "last_modified=excluded.last_modified, content_hash=excluded.content_hash, "
        "last_fetched_at=excluded.last_fetched_at",
        (url, r.headers.get("ETag"), r.headers.get("Last-Modified"), chash, db.now_kst()))
    conn.commit()
    if same:
        return None, True   # 본문 해시 동일 → 재분석 불필요
    return r, False


def html_to_text(html: str, limit: int = 20000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:limit]
