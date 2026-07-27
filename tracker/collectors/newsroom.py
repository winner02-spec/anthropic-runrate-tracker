# -*- coding: utf-8 -*-
"""Anthropic 공식 뉴스룸 수집기(사이트별 파서). 구조 변경 시 이 파서만 실패하고
전체 수집은 계속되도록 ingest 에서 예외 격리한다."""
from __future__ import annotations
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from tracker.collectors.base import Document, http_get, html_to_text


def collect_newsroom(url: str, source_name: str, tier: str, limit: int = 40) -> list[Document]:
    r = http_get(url)
    r.raise_for_status()
    try:
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        soup = BeautifulSoup(r.text, "html.parser")
    seen: set[str] = set()
    docs: list[Document] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if "/news/" not in href or href in seen:
            continue
        seen.add(href)
        title = " ".join(a.get_text(" ").split())
        if not title:
            continue
        docs.append(Document(title=title, url=href, text="", published_at=None,
                             source_name=source_name, tier=tier))
        if len(docs) >= limit:
            break
    return docs
