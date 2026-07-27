# -*- coding: utf-8 -*-
"""RSS / Google News RSS 수집기. feedparser 로 항목만 추출(본문은 ingest 에서 필요 시 fetch)."""
from __future__ import annotations
from urllib.parse import quote_plus
import feedparser

from tracker.collectors.base import Document
from tracker.extractors.dates import parse_published
from tracker.classifiers.source_tier import classify_tier


def google_news_url(query: str, lang: str = "en-US", country: str = "US") -> str:
    q = quote_plus(query)
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={lang}&gl={country}&ceid={country}:en")


def _entries(feed_url: str, source_name: str, default_tier: str, limit: int) -> list[Document]:
    parsed = feedparser.parse(feed_url)
    docs: list[Document] = []
    for e in parsed.entries[:limit]:
        link = e.get("link", "")
        pub = parse_published(e.get("published_parsed") or e.get("published")
                              or e.get("updated"))
        summary = e.get("summary", "") or ""
        # Google News 항목은 실제 매체 도메인으로 tier 재판정(가능하면)
        tier = classify_tier(link) if default_tier is None else default_tier
        if tier == "D" and default_tier:
            tier = default_tier
        docs.append(Document(title=e.get("title", ""), url=link, text=summary,
                             published_at=pub, source_name=source_name, tier=tier))
    return docs


def collect_rss(url: str, source_name: str, tier: str, limit: int = 40) -> list[Document]:
    return _entries(url, source_name, tier, limit)


def collect_google_news(query: str, source_name: str, tier: str, limit: int = 40) -> list[Document]:
    return _entries(google_news_url(query), source_name, tier, limit)
