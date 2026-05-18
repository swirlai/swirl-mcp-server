# Copyright (C) 2026 Sid Probstein
# Licensed under the Apache License, Version 2.0 — see LICENSE for details.
"""Runtime configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWIRL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = Field(default="http://localhost:8000")
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)
    verify_ssl: bool = Field(default=True)
    timeout_seconds: float = Field(default=30.0)
    rag_timeout_seconds: float = Field(default=60.0)
    max_results: int = Field(default=50, ge=1, le=200)
    default_providers: str | None = Field(default=None)

    @property
    def api_root(self) -> str:
        return self.base_url.rstrip("/") + "/api/swirl"

    @property
    def default_provider_list(self) -> list[str]:
        if not self.default_providers:
            return []
        return [p.strip() for p in self.default_providers.split(",") if p.strip()]


def load_settings() -> Settings:
    return Settings()
