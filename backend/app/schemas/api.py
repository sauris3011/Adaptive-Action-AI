"""Request/response models for the HTTP surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    graph_backend: str
    tls_warning: str | None = None


class TelemetrySummary(BaseModel):
    """Feeds the global header monitor (FR-13)."""

    active_calls: int
    total_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    cache_hits: int
    cache_misses: int
    cache_hit_ratio: float
    errors: int


class RuntimeSettings(BaseModel):
    """Settings drawer state (FR-14). The API key is never echoed back."""

    gateway_url: str
    gateway_api_key_set: bool
    ssl_verify: bool
    tls_warning: str | None = None
    models: dict[str, str]
    graph_backend: str


class RuntimeSettingsPatch(BaseModel):
    """US-8: change gateway config without a restart."""

    gateway_url: str | None = None
    gateway_api_key: str | None = None
    ssl_verify: bool | None = None


class SmokeRequest(BaseModel):
    prompt: str = Field(default="Reply with the single word: ready.", max_length=2000)


class SmokeResponse(BaseModel):
    """Stage 1 walking-skeleton probe: proves the full LLM path end to end."""

    reply: str
    model_role: str
