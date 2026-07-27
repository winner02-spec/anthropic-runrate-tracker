# -*- coding: utf-8 -*-
from tracker.dedup import canonical_url, normalize_title, content_hash, semantic_key


def test_canonical_url_strips_query():
    assert canonical_url("https://www.reuters.com/x/?utm_source=a#frag") == "https://reuters.com/x"


def test_normalize_title():
    assert normalize_title("Anthropic Hits $14B!!") == "anthropic hits 14b"


def test_content_hash_stable_and_sensitive():
    h1 = content_hash("https://a.com/x", "T", "2026-02-12", 14, None, "exact", "ev")
    h2 = content_hash("https://a.com/x", "T", "2026-02-12", 14, None, "exact", "ev")
    h3 = content_hash("https://a.com/x", "T", "2026-02-12", 47, None, "over", "ev")
    assert h1 == h2
    assert h1 != h3


def test_semantic_key_dedup_requote():
    # 같은 공식 발표를 두 매체가 재인용 → 같은 semantic_key
    k1 = semantic_key("company", "revenue_run_rate", 14, None, "exact", "2026-02-12", 1, 0, 0)
    k2 = semantic_key("company", "revenue_run_rate", 14, None, "exact", "2026-02-12", 1, 0, 0)
    assert k1 == k2
