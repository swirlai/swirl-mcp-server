# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
from __future__ import annotations

import pytest

from swirl_mcp import client as client_module
from swirl_mcp.config import Settings
from swirl_mcp.server import set_settings


@pytest.fixture(autouse=True)
def _clear_token_cache() -> None:
    """The token cache survives across SwirlClient instances; reset it per test."""
    client_module._TOKEN_CACHE.clear()


@pytest.fixture
def settings() -> Settings:
    s = Settings(
        base_url="http://swirl.test",
        username="admin",
        password="password",
        timeout_seconds=5.0,
        rag_timeout_seconds=5.0,
        max_results=25,
    )
    set_settings(s)
    return s


@pytest.fixture
def mock_login(httpx_mock):
    """Mock POST /swirl/login/ — required before any /sapi/ endpoint."""
    httpx_mock.add_response(
        method="POST",
        url="http://swirl.test/swirl/login/",
        json={"token": "test-token-abc123", "user": "admin"},
    )
    return "test-token-abc123"


@pytest.fixture
def search_envelope() -> dict:
    """A plausible SWIRL ``?qs=`` response with two providers and three hits."""
    return {
        "search_id": 42,
        "results": [
            {
                "title": "Sample hit one",
                "url": "https://example.com/1",
                "body": "Snippet for the first hit.",
                "searchprovider": "Arxiv",
                "swirl_score": 0.91,
                "date_published": "2025-04-01",
            },
            {
                "title": "Sample hit two",
                "url": "https://example.com/2",
                "body": ["List", "form", "body"],
                "searchprovider": "Europe PMC",
                "swirl_score": 0.73,
            },
            {
                "title": "Sample hit three",
                "url": "https://example.com/3",
                "body": "Snippet three.",
                "searchprovider": "Google News",
                "swirl_score": 0.62,
            },
        ],
    }
