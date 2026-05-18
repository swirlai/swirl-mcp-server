# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""Async HTTP client around the SWIRL REST API."""

from __future__ import annotations

from typing import Any

import httpx

from swirl_mcp.config import Settings


class SwirlError(RuntimeError):
    """Raised when SWIRL returns a non-successful response we cannot recover from."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class SwirlNotReady(RuntimeError):
    """Raised when SWIRL says a search exists but its results are not yet ready."""


# Cache tokens across SwirlClient instances so we don't re-login on every tool call.
# Keyed by (base_url, username) so the same process can multiplex users in HTTP mode.
_TOKEN_CACHE: dict[tuple[str, str], str] = {}


class SwirlClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._basic_auth = (
            httpx.BasicAuth(settings.username, settings.password)
            if settings.username and settings.password
            else None
        )
        self._transport = transport
        self._client = httpx.AsyncClient(
            base_url=settings.api_root,
            verify=settings.verify_ssl,
            timeout=settings.timeout_seconds,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> SwirlClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    # ---- public API ----------------------------------------------------------

    async def search_sync(
        self,
        query: str,
        providers: list[str] | None = None,
        result_mixer: str | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        """Run a federated search via ``?qs=`` and return the mixed result envelope."""
        params: dict[str, Any] = {"qs": query, "explain": str(explain).lower()}
        if providers:
            params["providers"] = ",".join(str(p) for p in providers)
        if result_mixer:
            params["result_mixer"] = result_mixer
        return await self._get("/search/", params=params)

    async def create_search(
        self,
        query: str,
        providers: list[str] | None = None,
        subscribe: bool = False,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query_string": query, "subscribe": subscribe}
        if providers is not None:
            body["searchprovider_list"] = providers
        if tags is not None:
            body["tags"] = tags
        return await self._post("/search/", json=body)

    async def list_searches(self, limit: int = 20) -> list[dict[str, Any]]:
        data = await self._get("/search/")
        items = data.get("results", data) if isinstance(data, dict) else data
        return list(items or [])[:limit]

    async def get_results(
        self,
        search_id: int,
        page: int = 1,
        result_mixer: str | None = None,
        provider: int | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "search_id": search_id,
            "page": page,
            "explain": str(explain).lower(),
        }
        if result_mixer:
            params["result_mixer"] = result_mixer
        if provider is not None:
            params["provider"] = provider
        return await self._get("/results/", params=params, allow_503=True)

    async def rag_answer(
        self,
        search_id: int,
        rag_items: list[int] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"search_id": search_id}
        if rag_items:
            params["rag_items"] = ",".join(str(i) for i in rag_items)
        return await self._get(
            "/sapi/detail-search-rag/",
            params=params,
            timeout=self.settings.rag_timeout_seconds,
        )

    async def list_providers(self) -> list[dict[str, Any]]:
        data = await self._get("/searchproviders/")
        items = data.get("results", data) if isinstance(data, dict) else data
        return list(items or [])

    # ---- low-level ----------------------------------------------------------

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
        allow_503: bool = False,
    ) -> Any:
        auth, headers = await self._auth_for(path)
        response = await self._client.get(
            path, params=params, timeout=timeout, auth=auth, headers=headers
        )
        return self._handle(response, allow_503=allow_503)

    async def _post(self, path: str, json: dict[str, Any]) -> Any:
        auth, headers = await self._auth_for(path)
        response = await self._client.post(path, json=json, auth=auth, headers=headers)
        return self._handle(response)

    async def _auth_for(self, path: str) -> tuple[httpx.Auth | None, dict[str, str]]:
        """SWIRL's TokenMiddleware gates `/sapi/` endpoints behind a DRF token,
        while the rest of the API uses Basic auth. Pick the right one per path.
        """
        if "/sapi/" in path:
            token = await self._ensure_token()
            return None, {"Authorization": f"Token {token}"}
        return self._basic_auth, {}

    async def _ensure_token(self) -> str:
        if not (self.settings.username and self.settings.password):
            raise SwirlError(
                "RAG/sapi endpoints require SWIRL_USERNAME and SWIRL_PASSWORD "
                "so the server can obtain a session token."
            )
        cache_key = (self.settings.base_url, self.settings.username)
        cached = _TOKEN_CACHE.get(cache_key)
        if cached:
            return cached

        login_url = self.settings.base_url.rstrip("/") + "/swirl/login/"
        async with httpx.AsyncClient(
            verify=self.settings.verify_ssl,
            timeout=self.settings.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(
                login_url,
                json={
                    "username": self.settings.username,
                    "password": self.settings.password,
                },
            )
        if response.status_code != 200:
            raise SwirlError(
                f"SWIRL login failed ({response.status_code}): {response.text[:200]}",
                status_code=response.status_code,
            )
        token = (response.json() or {}).get("token")
        if not token:
            raise SwirlError(
                "SWIRL login succeeded but returned no token — check the credentials."
            )
        _TOKEN_CACHE[cache_key] = token
        return token

    def _handle(self, response: httpx.Response, allow_503: bool = False) -> Any:
        if response.status_code == 401:
            raise SwirlError(
                "SWIRL rejected the credentials — check SWIRL_USERNAME and SWIRL_PASSWORD.",
                status_code=401,
            )
        if response.status_code == 403:
            raise SwirlError(
                "SWIRL denied access. The user lacks permission for this operation.",
                status_code=403,
            )
        if response.status_code == 404:
            raise SwirlError("SWIRL returned 404 — the requested object does not exist.", 404)
        if allow_503 and response.status_code == 503:
            raise SwirlNotReady("Results not ready yet — retry in a moment.")
        if response.status_code >= 400:
            text = response.text[:500] if response.text else ""
            raise SwirlError(
                f"SWIRL returned {response.status_code}: {text}",
                status_code=response.status_code,
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as err:
            raise SwirlError(f"SWIRL returned non-JSON body: {err}") from err
