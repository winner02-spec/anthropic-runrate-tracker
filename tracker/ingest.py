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


_CACHED = object()   # 캐시 히트 sentinel(재분석 불필요)


def _maybe_fetch_text_cached(conn, doc: Document, opts: dict):
    """본문 확보(조건부 GET). ETag/Last-Modified/content_hash 동일 시 _CACHED 반환(스킵)."""
    from tracker.collectors.base import conditional_get
    if not doc.url or "news.google.com" in doc.url:
        return doc.text  # 피드 요약만 사용(직접 fetch 불가)
    if doc.text and len(doc.text) > 400:
        return doc.text  # 이미 충분한 본문(요약) → 그대로
    r, cached = conditional_get(conn, doc.url, timeout=opts.get("request_timeout_sec", 25),
                                ua=opts.get("user_agent", "anthropic-runrate-tracker/0.1"))
    if cached:
        return _CACHED
    if r is not None and r.status_code == 200:
        return html_to_text(r.text)
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


def _within_recent_days(published_at, days: int) -> bool:
    if not published_at:
        return True   # 날짜 불명확은 통과(후단에서 처리)
    try:
        from datetime import date
        from dateutil import parser as dp
        d = dp.parse(str(published_at)).date()
        return (date.today() - d).days <= days
    except Exception:
        return True


def _register_source_candidate(conn, url: str, relevant: bool) -> None:
    """discovery: sources.yml 에 없는 도메인을 source_candidates 에 등록(자동 승격 금지)."""
    from tracker.classifiers.source_tier import domain_of, classify_tier
    dom = domain_of(url)
    if not dom:
        return
    if classify_tier(url) != "D":   # 이미 알려진(A/B/C) 도메인이면 후보 아님
        return
    now = db.now_kst()
    conn.execute(
        "INSERT INTO source_candidates(domain, source_name, first_seen_at, last_seen_at, "
        "discovery_count, relevant_article_count, status) VALUES(?,?,?,?,1,?, 'candidate') "
        "ON CONFLICT(domain) DO UPDATE SET last_seen_at=excluded.last_seen_at, "
        "discovery_count=discovery_count+1, "
        "relevant_article_count=relevant_article_count+excluded.relevant_article_count",
        (dom, dom, now, now, 1 if relevant else 0))
    conn.commit()


def run_collect(conn, mode: str = "daily", dry_run: bool = False) -> dict:
    from tracker import dedup
    data = _load_sources()
    opts = data.get("options", {})
    settings = config.settings()
    recent_days = int(settings.get("collect", {}).get("recent_days", 7))
    sources = [s for s in data.get("sources", []) if s.get("enabled", True)]
    started = db.now_kst()
    searched, errors = [], []
    docs_found = new_candidates = confirmed = duplicates = skipped_cached = 0
    seen_semantic = _existing_official_semantic(conn)   # 대표 공식원문 이후 재인용은 supporting

    for src in sources:
        searched.append(src.get("name"))
        try:
            docs = _collect_from_source(src, opts)
        except Exception as e:  # 소스 격리
            errors.append(f"{src.get('name')}: {repr(e)[:160]}")
            continue
        for doc in docs:
            # daily: 최근 N일만
            if mode == "daily" and not _within_recent_days(doc.published_at, recent_days):
                continue
            docs_found += 1
            try:
                text = _maybe_fetch_text_cached(conn, doc, opts)
                if text is _CACHED:
                    skipped_cached += 1
                    continue   # ETag/Last-Modified/content_hash 동일 → 재분석 스킵(토큰 절감)
                cands = build_candidates(title=doc.title, url=doc.url, text=text,
                                         published_at=doc.published_at,
                                         source_name=doc.source_name, tier=doc.tier or "D")
            except Exception as e:  # 문서 격리
                errors.append(f"doc {doc.url[:60]}: {repr(e)[:120]}")
                continue
            if mode == "discovery":
                # 새 도메인 등록만(숫자 자동확정 안 함). 후보는 review 로.
                _register_source_candidate(conn, doc.url, relevant=bool(cands))
                for c in cands:
                    c.status = config.STATUS_NEEDS_REVIEW
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
                # 피드백 재사용: 과거 오분류/거절 이력 있는 도메인은 자동확정 막고 review 로
                if c.status == config.STATUS_CONFIRMED:
                    from tracker.classifiers.source_tier import domain_of
                    from tracker.classifiers import feedback
                    if feedback.domain_should_review(conn, domain_of(c.source_url or "")):
                        c.status = config.STATUS_NEEDS_REVIEW
                        c.source_type = (c.source_type or "") + "|feedback_review"
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
            "started_at": started, "finished_at": finished, "mode": mode,
            "sources_searched": json.dumps(searched, ensure_ascii=False),
            "docs_found": docs_found, "new_candidates": new_candidates,
            "confirmed": confirmed, "duplicates": duplicates,
            "skipped_cached": skipped_cached, "api_calls": 0, "est_tokens": 0,
            "errors": json.dumps(errors, ensure_ascii=False),
        })
    return {"mode": mode, "docs_found": docs_found, "new_candidates": new_candidates,
            "confirmed": confirmed, "duplicates": duplicates, "skipped_cached": skipped_cached,
            "api_calls": 0, "est_tokens": 0, "errors": errors, "searched": searched}


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
