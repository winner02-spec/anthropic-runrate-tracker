# -*- coding: utf-8 -*-
from tracker.classifiers.source_tier import classify_tier
from tracker.classifiers.statement import classify


def test_tier_mapping():
    assert classify_tier("https://www.anthropic.com/news/series-h") == "A"
    assert classify_tier("https://www.reuters.com/tech/x") == "B"
    assert classify_tier("https://sacra.com/c/anthropic/") == "C"
    assert classify_tier("https://x.com/AnthropicAI/status/1") == "D"
    assert classify_tier("https://some-unknown-blog.example/x") == "D"


def test_official_vs_estimate_separation():
    a = classify("A", "exact", "Anthropic said run-rate revenue is $14B", runrate_context=True)
    assert a.is_official and not a.is_estimate
    assert a.auto_confirmable  # Tier A 명확 run-rate → 자동확정 가능

    c = classify("C", "exact", "our model implies about $20B", runrate_context=True)
    assert c.is_estimate and not c.is_official
    assert not c.auto_confirmable

    t = classify("A", "target", "targeting $20B by year end", runrate_context=True)
    assert t.is_target and not t.is_official
    assert not t.auto_confirmable

    d = classify("D", "exact", "someone tweeted $30B", runrate_context=True)
    assert d.source_type == "social" and not d.auto_confirmable
