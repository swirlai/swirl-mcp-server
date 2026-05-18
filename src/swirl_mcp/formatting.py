# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""Reshape SWIRL's verbose result envelopes into lean, LLM-friendly payloads."""

from __future__ import annotations

from typing import Any

from swirl_mcp.models import NormalizedResult, ProviderSummary, SearchSummary

SNIPPET_MAX_CHARS = 600


def _truncate(text: str, limit: int = SNIPPET_MAX_CHARS) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def normalize_result(raw: dict[str, Any]) -> NormalizedResult:
    """Map a single SWIRL result hit to the trimmed schema.

    SWIRL hits vary by connector — common fields are title/url/body/snippet/date_published
    plus a ``swirl_score`` injected by the relevancy processor.
    """
    body = raw.get("body") or raw.get("snippet") or raw.get("summary") or ""
    if isinstance(body, list):
        body = " ".join(str(item) for item in body if item)

    return NormalizedResult(
        title=str(raw.get("title") or "").strip(),
        snippet=_truncate(str(body)),
        url=str(raw.get("url") or raw.get("link") or "").strip(),
        source=str(raw.get("searchprovider") or raw.get("source") or "").strip(),
        relevancy_score=_score(raw),
        date_published=str(raw.get("date_published") or "").strip() or None,
        result_id=raw.get("swirl_id") or raw.get("id"),
    )


def _score(raw: dict[str, Any]) -> float | None:
    for key in ("swirl_score", "score", "relevancy"):
        if key in raw and raw[key] is not None:
            try:
                return float(raw[key])
            except (TypeError, ValueError):
                continue
    return None


def normalize_results_envelope(envelope: Any) -> list[NormalizedResult]:
    """SWIRL returns results either as a list or wrapped in a paginated dict."""
    if envelope is None:
        return []
    # paginated form: {"count": N, "results": [...]} vs flat list
    items = (
        envelope.get("results", envelope.get("items", []))
        if isinstance(envelope, dict)
        else envelope
    )

    hits: list[NormalizedResult] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        # SWIRL mixed results carry per-provider blocks under 'results' too
        if "title" in item or "url" in item or "body" in item:
            hits.append(normalize_result(item))
        elif "results" in item and isinstance(item["results"], list):
            source = item.get("searchprovider") or item.get("source") or ""
            for sub in item["results"]:
                if isinstance(sub, dict):
                    sub.setdefault("searchprovider", source)
                    hits.append(normalize_result(sub))
    return hits


def normalize_provider(raw: dict[str, Any]) -> ProviderSummary:
    return ProviderSummary(
        id=int(raw.get("id", 0)),
        name=str(raw.get("name", "")),
        connector=str(raw.get("connector", "")),
        active=bool(raw.get("active", False)),
        default=bool(raw.get("default", False)),
        tags=list(raw.get("tags") or []),
    )


def normalize_search(raw: dict[str, Any]) -> SearchSummary:
    return SearchSummary(
        id=int(raw.get("id", 0)),
        query_string=str(raw.get("query_string", "")),
        status=str(raw.get("status", "")),
        date_created=str(raw.get("date_created", "")),
        result_mixer=str(raw.get("result_mixer", "")),
    )


def markdown_summary(results: list[NormalizedResult], answer: str | None = None) -> str:
    """Render a compact markdown view suitable for display in an MCP client."""
    lines: list[str] = []
    if answer:
        lines.append("## Answer\n")
        lines.append(answer.strip())
        lines.append("\n## Sources\n")
    if not results:
        lines.append("_No results._")
        return "\n".join(lines)
    for i, r in enumerate(results, start=1):
        title = r.title or "(untitled)"
        head = f"{i}. [{title}]({r.url})" if r.url else f"{i}. {title}"
        meta_bits = []
        if r.source:
            meta_bits.append(r.source)
        if r.relevancy_score is not None:
            meta_bits.append(f"score {r.relevancy_score:.2f}")
        if r.date_published:
            meta_bits.append(r.date_published)
        if meta_bits:
            head += f" — _{' · '.join(meta_bits)}_"
        lines.append(head)
        if r.snippet:
            lines.append(f"   > {r.snippet}")
    return "\n".join(lines)
