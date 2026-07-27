# -*- coding: utf-8 -*-
"""수집 오케스트레이션: sources.yml → 수집기 → 파이프라인 → DB.

· 소스/문서별 예외 격리(하나 실패해도 전체 계속).
· 자동확정(Tier A + 명확 run-rate) 은 runrate_updates(status=confirmed).
· 그 외는 runrate_updates(status=needs_review) + review_queue 등록.
· 동일 content_hash 는 중복으로 건너뜀.
"""
from __future__ import annotations
import json
import yaml

from tracker import config
from tracker.database import db
from tracker.pipeline import build_candidates
from tracker.collectors.base import Document, http_get, html_to_text
from tracker.collectors import feeds, newsroom


def _load_sources() -> dict:
    return yaml.safe_load(config.SOURCES_YML.read_text(encoding="utf-8")) or {}


def _collect_from_source(src: dict, opts: dict) -> list[Document]:
    typ = src.get("type")
    name = src.get("name", typ)
    tier = src.get("tier")
    limit = opts.get("max_articles_per_source", 40)
    if typ == "rss":
        return feeds.collect_rss(src["url"], name, tier or "B", limit)
    if typ == "google_news":
        return feeds.collect_google_news(src["query"], name, tier or "B", limit)
    if typ == "newsroom":
        return newsroom.collect_newsroom(src["url"], name, tier or "A", limit)
    if typ == "manual_urls":
        return _collect_manual_urls(src, name, limit)
    return []


def _collect_manual_urls(src: dict, name: str, limit: int) -> list[Document]:
    from tracker.classifiers.source_tier import classify_tier
    path = config.BASE_DIR / src.get("file", "config/manual_urls.txt")
    docs: list[Document] = []
    if not path.exists():
        return docs
    for line in path.read_text(encoding="utf-8").splitlines():
        url = line.strip()
        if not url or url.startswith("#"):
            continue
        docs.append(Document(title="", url=url, text="", published_at=None,
                             source_name=name, tier=classify_tier(url)))
    return docs[:limit]


def _maybe_fetch_text(doc: Document, opts: dict) -> str:
    """본문이 비었고 직접 기사 URL 이면 best-effort 로 텍스트 확보(격리)."""
    if doc.text and len(doc.text) > 120:
        return doc.text
    if not doc.url or "news.google.com" in doc.url:
        return doc.text
    try:
        r = http_get(doc.url, timeout=opts.get("request_timeout_sec", 25),
                     ua=opts.get("user_agent", "anthropic-runrate-tracker/0.1"))
        if r.status_code == 200:
            return html_to_text(r.text)
    except Exception:
        return doc.text
    return doc.text


def _existing_official_semantic(conn) -> set:
    """이미 확정된 공식 포인트의 semantic_key 집합(재인용 중복 방지용)."""
    from tracker import dedup
    keys = set()
    for r in db.fetchall(conn, "SELECT * FROM runrate_updates WHERE status=? AND is_official=1",
                         (config.STATUS_CONFIRMED,)):
        d = dict(r)
        keys.add(dedup.semantic_key(d["metric_scope"], d["metric_type"], d["value_low_usd_bn"],
                                    d["value_high_usd_bn"], d["qualifier"], d["as_of_end"],
                                    d["is_official"], d["is_estimate"], d["is_target"]))
    return keys


def run_collect(conn, dry_run: bool = False) -> dict:
    from tracker import dedup
    data = _load_sources()
    opts = data.get("options", {})
    sources = [s for s in data.get("sources", []) if s.get("enabled", True)]
    started = db.now_kst()
    searched, errors = [], []
    docs_found = new_candidates = confirmed = duplicates = 0
    seen_semantic = _existing_official_semantic(conn)   # 대표 공식원문 이후 재인용은 supporting

    for src in sources:
        searched.append(src.get("name"))
        try:
            docs = _collect_from_source(src, opts)
        except Exception as e:  # 소스 격리
            errors.append(f"{src.get('name')}: {repr(e)[:160]}")
            continue
        for doc in docs:
            docs_found += 1
            try:
                text = _maybe_fetch_text(doc, opts)
                cands = build_candidates(title=doc.title, url=doc.url, text=text,
                                         published_at=doc.published_at,
                                         source_name=doc.source_name, tier=doc.tier or "D")
            except Exception as e:  # 문서 격리
                errors.append(f"doc {doc.url[:60]}: {repr(e)[:120]}")
                continue
            for c in cands:
                if db.exists_hash(conn, "runrate_updates", c.content_hash):
                    duplicates += 1
                    continue
                # 재인용 중복: 같은 공식 수치(값·기준일)면 대표 1개만 확정, 나머지는 supporting(needs_review)
                if c.status == config.STATUS_CONFIRMED and c.is_official:
                    sk = dedup.semantic_key(c.metric_scope, c.metric_type, c.value_low_usd_bn,
                                            c.value_high_usd_bn, c.qualifier, c.as_of_end,
                                            c.is_official, c.is_estimate, c.is_target)
                    if sk in seen_semantic:
                        c.status = config.STATUS_NEEDS_REVIEW   # supporting source
                        c.source_type = (c.source_type or "") + "|supporting"
                    else:
                        seen_semantic.add(sk)
                if dry_run:
                    new_candidates += 1
                    continue
                row = c.to_row()
                now = db.now_kst()
                row["created_at"] = now
                row["updated_at"] = now
                rid = db.insert(conn, "runrate_updates", row)
                if rid is None:
                    duplicates += 1
                    continue
                new_candidates += 1
                if c.status == config.STATUS_CONFIRMED:
                    confirmed += 1
                else:
                    _enqueue_review(conn, rid, c, now)

    finished = db.now_kst()
    if not dry_run:
        db.insert(conn, "ingestion_runs", {
            "started_at": started, "finished_at": finished,
            "sources_searched": json.dumps(searched, ensure_ascii=False),
            "docs_found": docs_found, "new_candidates": new_candidates,
            "confirmed": confirmed, "duplicates": duplicates,
            "errors": json.dumps(errors, ensure_ascii=False),
        })
    return {"docs_found": docs_found, "new_candidates": new_candidates,
            "confirmed": confirmed, "duplicates": duplicates, "errors": errors,
            "searched": searched}


def _enqueue_review(conn, runrate_id: int, c, now: str) -> None:
    from tracker import dedup
    ch = dedup.content_hash(c.source_url or "", "rq", c.published_at,
                            c.value_low_usd_bn, c.value_high_usd_bn, c.qualifier,
                            c.evidence_text)
    db.insert(conn, "review_queue", {
        "runrate_update_id": runrate_id, "kind": "runrate",
        "found_expression": c.original_value, "classification": c.source_type,
        "source_name": c.source_name, "source_url": c.source_url, "source_tier": c.source_tier,
        "confidence_score": c.confidence_score, "evidence_text": c.evidence_text,
        "published_at": c.published_at, "as_of_start": c.as_of_start, "as_of_end": c.as_of_end,
        "payload_json": json.dumps(c.to_row(), ensure_ascii=False),
        "content_hash": ch, "status": "pending", "created_at": now,
    })
