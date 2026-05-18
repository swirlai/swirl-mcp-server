# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""Pydantic models for tool inputs and outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ResultMixer = Literal[
    "RelevancyMixer",
    "RelevancyNewItemsMixer",
    "DateMixer",
    "DateNewItemsMixer",
    "RoundRobinMixer",
    "Stack1Mixer",
    "Stack2Mixer",
    "Stack3Mixer",
    "StackNMixer",
]


class NormalizedResult(BaseModel):
    """A single search hit, trimmed to the fields an LLM actually uses."""

    title: str = ""
    snippet: str = ""
    url: str = ""
    source: str = ""
    relevancy_score: float | None = None
    date_published: str | None = None
    result_id: int | None = None


class SearchResponse(BaseModel):
    search_id: int | None = None
    query: str
    results: list[NormalizedResult]
    answer: str | None = None
    page: int = 1
    total_results: int | None = None


class ProviderSummary(BaseModel):
    id: int
    name: str
    connector: str
    active: bool
    default: bool
    tags: list[str] = Field(default_factory=list)


class SearchSummary(BaseModel):
    id: int
    query_string: str
    status: str
    date_created: str
    result_mixer: str
