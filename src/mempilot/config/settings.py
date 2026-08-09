"""Validated application settings models."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mempilot.i18n import Language


class ScanSettings(BaseModel):
    """Persistent defaults mirroring scan options."""

    model_config = ConfigDict(extra="forbid")

    alignment: int = Field(default=0, ge=0)
    writable_only: bool = True
    include_image: bool = True
    include_mapped: bool = False
    use_tolerance: bool = True
    float_tolerance: float = Field(default=0.001, ge=0.0)
    case_sensitive: bool = True
    chunk_size: int = Field(default=4 << 20, ge=1)
    max_candidates: int = Field(default=10_000_000, ge=1)
    unknown_budget_mb: int = Field(default=512, ge=1)
    address_min: int = Field(default=0, ge=0)
    address_max: int = Field(default=0x7FFF_FFFE_FFFF, ge=0)


class UISettings(BaseModel):
    """Persistent user-interface refresh and paging settings."""

    model_config = ConfigDict(extra="forbid")

    results_page_size: int = Field(default=1000, ge=1)
    results_refresh_ms: int = Field(default=500, ge=50, le=5000)
    watch_refresh_ms: int = Field(default=100, ge=50, le=5000)
    show_system_processes: bool = False
    language: Language = Language.SPANISH


class CLIBackend(StrEnum):
    """Supported authenticated command-line AI providers."""

    ANTIGRAVITY = "agy"
    CODEX = "codex"
    CLAUDE = "claude"


class AISettings(BaseModel):
    """Persistent CLI provider settings; API credentials are never accepted."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    provider: CLIBackend = CLIBackend.CODEX
    executable: str | None = None
    model: str | None = None
    timeout_s: float = Field(default=180.0, gt=0.0)
    autonomous_write_limit: int = Field(default=20, ge=0)
    confirmation_timeout_s: float = Field(default=120.0, gt=0.0)


class Settings(BaseModel):
    """Versioned root settings document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    scan: ScanSettings = Field(default_factory=ScanSettings)
    ui: UISettings = Field(default_factory=UISettings)
    ai: AISettings = Field(default_factory=AISettings)
