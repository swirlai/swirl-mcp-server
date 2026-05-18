# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
import pytest

from swirl_mcp.client import SwirlClient, SwirlError, SwirlNotReady


async def test_search_sync_sends_qs_and_providers(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/search/?qs=rag&explain=false&providers=arxiv%2C7",
        json={"search_id": 5, "results": []},
    )
    async with SwirlClient(settings) as client:
        data = await client.search_sync(query="rag", providers=["arxiv", 7])
    assert data == {"search_id": 5, "results": []}


async def test_get_results_translates_503_to_not_ready(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/results/?search_id=42&page=1&explain=false",
        status_code=503,
        text="Result Object Not Ready Yet",
    )
    async with SwirlClient(settings) as client:
        with pytest.raises(SwirlNotReady):
            await client.get_results(search_id=42)


async def test_401_raises_credentialed_error(settings, httpx_mock):
    httpx_mock.add_response(method="GET", url="http://swirl.test/api/swirl/searchproviders/", status_code=401)
    async with SwirlClient(settings) as client:
        with pytest.raises(SwirlError) as excinfo:
            await client.list_providers()
    assert excinfo.value.status_code == 401
    assert "credentials" in str(excinfo.value).lower()


async def test_403_raises_permission_error(settings, httpx_mock):
    httpx_mock.add_response(method="GET", url="http://swirl.test/api/swirl/search/", status_code=403)
    async with SwirlClient(settings) as client:
        with pytest.raises(SwirlError) as excinfo:
            await client.list_searches()
    assert excinfo.value.status_code == 403


async def test_create_search_posts_json_body(settings, httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="http://swirl.test/api/swirl/search/",
        json={"id": 99, "status": "NEW_SEARCH"},
    )
    async with SwirlClient(settings) as client:
        out = await client.create_search(query="hello", providers=["arxiv"], tags=["t1"])
    assert out["id"] == 99
    request = httpx_mock.get_request()
    body = request.content.decode()
    assert '"query_string":"hello"' in body
    assert '"searchprovider_list":["arxiv"]' in body
    assert '"tags":["t1"]' in body


async def test_rag_answer_uses_rag_timeout(settings, mock_login, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/sapi/detail-search-rag/?search_id=11&rag_items=1%2C2",
        json={"message": "The answer."},
    )
    async with SwirlClient(settings) as client:
        out = await client.rag_answer(search_id=11, rag_items=[1, 2])
    assert out["message"] == "The answer."

    rag_request = next(
        r for r in httpx_mock.get_requests() if "/sapi/" in str(r.url)
    )
    assert rag_request.headers.get("Authorization") == f"Token {mock_login}"


async def test_sapi_call_without_credentials_raises(httpx_mock):
    from swirl_mcp.config import Settings

    bare = Settings(base_url="http://swirl.test", username=None, password=None)
    async with SwirlClient(bare) as client:
        with pytest.raises(SwirlError) as excinfo:
            await client.rag_answer(search_id=1)
    assert "USERNAME" in str(excinfo.value)


async def test_list_providers_unwraps_paginated_envelope(settings, httpx_mock):
    httpx_mock.add_response(
        method="GET",
        url="http://swirl.test/api/swirl/searchproviders/",
        json={"count": 1, "results": [{"id": 1, "name": "Arxiv", "connector": "RequestsGet"}]},
    )
    async with SwirlClient(settings) as client:
        out = await client.list_providers()
    assert out == [{"id": 1, "name": "Arxiv", "connector": "RequestsGet"}]
