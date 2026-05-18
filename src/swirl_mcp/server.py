# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""FastMCP entrypoint — wires tools, resources, and prompts to a SwirlClient."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from swirl_mcp.client import SwirlClient, SwirlError, SwirlNotReady
from swirl_mcp.config import Settings, load_settings
from swirl_mcp.formatting import (
    markdown_summary,
    normalize_provider,
    normalize_results_envelope,
    normalize_search,
)
from swirl_mcp.models import ResultMixer, SearchResponse

logger = logging.getLogger("swirl_mcp")

mcp = FastMCP(
    "swirl-mcp-server",
    instructions=(
        "Federated search and RAG over the user's configured SWIRL connectors. "
        "Use `search` for one-shot Q&A (set rag=True to get a generated answer with citations); "
        "use `create_search` + `get_results` for long-running or subscribed searches; "
        "use `list_providers` to discover what sources are available."
    ),
)

_SETTINGS_CACHE: Settings | None = None


def _settings() -> Settings:
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is None:
        _SETTINGS_CACHE = load_settings()
    return _SETTINGS_CACHE


def set_settings(settings: Settings) -> None:
    """Override the cached settings — primarily for tests and the CLI entrypoint."""
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = settings


def _resolve_providers(providers: list[str] | None) -> list[str] | None:
    if providers:
        return [str(p) for p in providers]
    defaults = _settings().default_provider_list
    return defaults or None


def _cap_count(n: int) -> int:
    return max(1, min(n, _settings().max_results))


# ---- tools -------------------------------------------------------------------


@mcp.tool()
async def search(
    query: Annotated[str, Field(description="What to search for.")],
    providers: Annotated[
        list[str] | None,
        Field(description="Provider ids, names, or tags. Omit to use defaults."),
    ] = None,
    result_count: Annotated[int, Field(ge=1, le=200, description="Max results to return.")] = 10,
    rag: Annotated[bool, Field(description="If true, also return a generated answer.")] = False,
    explain: Annotated[bool, Field(description="Include relevancy explanations.")] = False,
    result_mixer: Annotated[
        ResultMixer | None, Field(description="Override the result mixer.")
    ] = None,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """Run a federated SWIRL search and return ranked, mixed results.

    With ``rag=True`` the top results are passed to SWIRL's RAG processor and the
    generated answer is included alongside its sources.
    """
    settings = _settings()
    limit = _cap_count(result_count)
    async with SwirlClient(settings) as client:
        envelope = await client.search_sync(
            query=query,
            providers=_resolve_providers(providers),
            result_mixer=result_mixer,
            explain=explain,
        )
        results = normalize_results_envelope(envelope)[:limit]
        search_id = _extract_search_id(envelope, results)
        answer: str | None = None
        if rag and search_id is not None:
            try:
                rag_payload = await client.rag_answer(search_id=search_id)
                answer = (rag_payload or {}).get("message") or None
            except SwirlError as err:
                if ctx:
                    await ctx.warning(f"RAG step failed: {err}")
                answer = None

    response = SearchResponse(
        search_id=search_id,
        query=query,
        results=results,
        answer=answer,
        total_results=len(results),
    )
    return {
        "structured": response.model_dump(),
        "markdown": markdown_summary(results, answer=answer),
    }


@mcp.tool()
async def create_search(
    query: Annotated[str, Field(description="What to search for.")],
    providers: Annotated[list[str] | None, Field(description="Provider ids/names/tags.")] = None,
    subscribe: Annotated[bool, Field(description="Keep the search updating with new hits.")] = False,
    tags: Annotated[list[str] | None, Field(description="Tags to attach to the search.")] = None,
) -> dict[str, Any]:
    """Create a search asynchronously and return its id. Poll with ``get_results``."""
    async with SwirlClient(_settings()) as client:
        payload = await client.create_search(
            query=query,
            providers=_resolve_providers(providers),
            subscribe=subscribe,
            tags=tags,
        )
    return {
        "search_id": payload.get("id"),
        "status": payload.get("status", "NEW_SEARCH"),
        "next": "Call get_results(search_id=...) to fetch ranked results.",
    }


@mcp.tool()
async def get_results(
    search_id: Annotated[int, Field(ge=1, description="The SWIRL search id.")],
    page: Annotated[int, Field(ge=1, description="1-based page index.")] = 1,
    result_count: Annotated[int, Field(ge=1, le=200)] = 10,
    result_mixer: Annotated[ResultMixer | None, Field(description="Override the mixer.")] = None,
    provider: Annotated[int | None, Field(description="Filter results to one provider.")] = None,
    explain: Annotated[bool, Field(description="Include relevancy explanations.")] = False,
) -> dict[str, Any]:
    """Fetch (or re-mix) results for an existing search. Returns ``not_ready`` if still running."""
    async with SwirlClient(_settings()) as client:
        try:
            envelope = await client.get_results(
                search_id=search_id,
                page=page,
                result_mixer=result_mixer,
                provider=provider,
                explain=explain,
            )
        except SwirlNotReady:
            return {"status": "not_ready", "search_id": search_id, "retry_in_seconds": 1}

    results = normalize_results_envelope(envelope)[: _cap_count(result_count)]
    response = SearchResponse(
        search_id=search_id,
        query="",
        results=results,
        page=page,
        total_results=len(results),
    )
    return {
        "structured": response.model_dump(),
        "markdown": markdown_summary(results),
    }


@mcp.tool()
async def rag_answer(
    search_id: Annotated[int, Field(ge=1, description="The SWIRL search id.")],
    result_ids: Annotated[
        list[int] | None,
        Field(description="Optional subset of result ids to include in the prompt."),
    ] = None,
) -> dict[str, Any]:
    """Generate a RAG answer over an existing SWIRL search."""
    async with SwirlClient(_settings()) as client:
        payload = await client.rag_answer(search_id=search_id, rag_items=result_ids)
    return {
        "search_id": search_id,
        "answer": (payload or {}).get("message", ""),
    }


@mcp.tool()
async def list_providers(
    active_only: Annotated[bool, Field(description="Hide inactive providers.")] = True,
    tag: Annotated[str | None, Field(description="Optional tag filter.")] = None,
) -> dict[str, Any]:
    """List the user's configured SWIRL SearchProviders (no credentials returned)."""
    async with SwirlClient(_settings()) as client:
        raw = await client.list_providers()
    providers = [normalize_provider(p) for p in raw]
    if active_only:
        providers = [p for p in providers if p.active]
    if tag:
        providers = [p for p in providers if tag in p.tags]
    return {"providers": [p.model_dump() for p in providers], "count": len(providers)}


@mcp.tool()
async def list_searches(
    limit: Annotated[int, Field(ge=1, le=200, description="Max searches to return.")] = 20,
) -> dict[str, Any]:
    """List the user's recent SWIRL searches."""
    async with SwirlClient(_settings()) as client:
        raw = await client.list_searches(limit=limit)
    searches = [normalize_search(s).model_dump() for s in raw]
    return {"searches": searches, "count": len(searches)}


# ---- resources & prompts -----------------------------------------------------


@mcp.resource("swirl://providers")
async def providers_resource() -> str:
    """JSON dump of the active SearchProvider catalog."""
    async with SwirlClient(_settings()) as client:
        raw = await client.list_providers()
    providers = [normalize_provider(p).model_dump() for p in raw]
    return json.dumps({"providers": providers}, indent=2)


@mcp.prompt()
def swirl_research(question: str) -> str:
    """Reusable prompt: answer a question by calling `search` with rag=True."""
    return (
        "Use the `search` tool with `rag=true` to answer the following question. "
        "Cite every source by its title and url from the returned results. "
        "If no results are found, say so plainly rather than guessing.\n\n"
        f"Question: {question}"
    )


# ---- helpers -----------------------------------------------------------------


def _extract_search_id(envelope: Any, results: list) -> int | None:
    """Pull a search id from either the envelope or the first hit."""
    if isinstance(envelope, dict):
        for key in ("search_id", "id"):
            if key in envelope and isinstance(envelope[key], int):
                return envelope[key]
    for r in results:
        if r.result_id and isinstance(r.result_id, int):
            return None  # result_id is per-hit, not search-level
    return None


# ---- entrypoint --------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="swirl-mcp", description="SWIRL MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging to stderr."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    set_settings(load_settings())

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
