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


def html_to_text(html: str, limit: int = 20000) -> str:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:limit]
