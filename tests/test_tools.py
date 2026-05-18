# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""Higher-level tests that exercise the tool functions end-to-end with mocked HTTP."""

import re

from swirl_mcp import server


async def test_search_tool_returns_structured_and_markdown(settings, httpx_mock, search_envelope):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"http://swirl\.test/api/swirl/search/\?.*"),
        json=search_envelope,
    )
    out = await server.search(query="rag", result_count=10)
    assert "structured" in out
    assert "markdown" in out
    structured = out["structured"]
    assert structured["search_id"] == 42
    assert len(structured["results"]) == 3
    assert structured["results"][0]["source"] == "Arxiv"
    assert "[Sample hit one](https://example.com/1)" in out["markdown"]


async def test_search_tool_with_rag_calls_rag_endpoint(settings, mock_login, httpx_mock, search_envelope):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"http://swirl\.test/api/swirl/search/\?.*"),
        json=search_envelope,
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"http://swirl\.test/api/swirl/sapi/detail-search-rag/\?.*"),
        json={"message": "Composed answer."},
    )
    out = await server.search(query="rag", rag=True)
    assert out["structured"]["answer"] == "Composed answer."
    assert "## Answer" in out["markdown"]


async def test_get_results_not_ready_returns_status(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"http://swirl\.test/api/swirl/results/\?.*"),
        status_code=503,
    )
    out = await server.get_results(search_id=42)
    assert out == {"status": "not_ready", "search_id": 42, "retry_in_seconds": 1}


async def test_list_providers_filters_inactive(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/searchproviders/",
        json=[
            {"id": 1, "name": "A", "connector": "RequestsGet", "active": True, "default": True, "tags": []},
            {"id": 2, "name": "B", "connector": "RequestsGet", "active": False, "default": False, "tags": []},
        ],
    )
    out = await server.list_providers(active_only=True)
    assert out["count"] == 1
    assert out["providers"][0]["name"] == "A"


async def test_list_providers_filters_by_tag(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/searchproviders/",
        json=[
            {"id": 1, "name": "A", "connector": "X", "active": True, "default": True, "tags": ["academic"]},
            {"id": 2, "name": "B", "connector": "X", "active": True, "default": True, "tags": ["news"]},
        ],
    )
    out = await server.list_providers(active_only=True, tag="news")
    assert out["count"] == 1
    assert out["providers"][0]["name"] == "B"


def test_swirl_research_prompt_contains_question():
    text = server.swirl_research(question="What is SWIRL?")
    assert "What is SWIRL?" in text
    assert "rag=true" in text
