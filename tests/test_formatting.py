# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
from swirl_mcp.formatting import (
    SNIPPET_MAX_CHARS,
    markdown_summary,
    normalize_provider,
    normalize_result,
    normalize_results_envelope,
    normalize_search,
)


def test_normalize_result_basic():
    raw = {
        "title": "  Hello  ",
        "url": "https://x.test/1",
        "body": "Some body text",
        "searchprovider": "Arxiv",
        "swirl_score": "0.5",
        "date_published": "2025-01-01",
        "swirl_id": 7,
    }
    r = normalize_result(raw)
    assert r.title == "Hello"
    assert r.url == "https://x.test/1"
    assert r.snippet == "Some body text"
    assert r.source == "Arxiv"
    assert r.relevancy_score == 0.5
    assert r.date_published == "2025-01-01"
    assert r.result_id == 7


def test_normalize_result_handles_list_body():
    r = normalize_result({"title": "t", "body": ["foo", "bar", None]})
    assert r.snippet == "foo bar"


def test_normalize_result_truncates_long_snippet():
    long_text = "x" * (SNIPPET_MAX_CHARS + 200)
    r = normalize_result({"title": "t", "body": long_text})
    assert len(r.snippet) <= SNIPPET_MAX_CHARS
    assert r.snippet.endswith("…")


def test_normalize_results_envelope_flat_list(search_envelope):
    hits = normalize_results_envelope(search_envelope["results"])
    assert len(hits) == 3
    assert hits[0].source == "Arxiv"
    assert hits[1].snippet == "List form body"


def test_normalize_results_envelope_dict_with_results(search_envelope):
    hits = normalize_results_envelope(search_envelope)
    assert len(hits) == 3


def test_normalize_results_envelope_nested_per_provider():
    envelope = [
        {
            "searchprovider": "FooSource",
            "results": [
                {"title": "a", "url": "u1", "body": "b1"},
                {"title": "b", "url": "u2", "body": "b2"},
            ],
        }
    ]
    hits = normalize_results_envelope(envelope)
    assert [h.source for h in hits] == ["FooSource", "FooSource"]


def test_normalize_results_envelope_empty():
    assert normalize_results_envelope(None) == []
    assert normalize_results_envelope([]) == []


def test_normalize_provider_strips_credentials():
    raw = {
        "id": 3,
        "name": "Arxiv",
        "connector": "RequestsGet",
        "active": True,
        "default": False,
        "tags": ["academic"],
        "credentials": "SECRET",
        "url": "https://arxiv.org",
    }
    p = normalize_provider(raw)
    dumped = p.model_dump()
    assert "credentials" not in dumped
    assert "url" not in dumped
    assert dumped["tags"] == ["academic"]


def test_normalize_search():
    s = normalize_search(
        {
            "id": 11,
            "query_string": "rag",
            "status": "FULL_RESULTS_READY",
            "date_created": "2025-05-17",
            "result_mixer": "RelevancyMixer",
        }
    )
    assert s.id == 11
    assert s.status == "FULL_RESULTS_READY"


def test_markdown_summary_with_answer_and_results(search_envelope):
    hits = normalize_results_envelope(search_envelope)
    md = markdown_summary(hits, answer="The answer is 42.")
    assert "## Answer" in md
    assert "The answer is 42." in md
    assert "[Sample hit one](https://example.com/1)" in md
    assert "score 0.91" in md


def test_markdown_summary_empty():
    md = markdown_summary([])
    assert "_No results._" in md
