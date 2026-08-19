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
    # Health rides the telemetry poll rather than a second timer: the header
    # already asks this endpoint every 1.5s, and two pollers for one strip of
    # the header is a moving part with no user-visible benefit.
    graph_backend: str = "unselected"
    graph_fallback: bool = False
    gateway_enabled: bool = True


class RuntimeSettings(BaseModel):
    """Settings drawer state (FR-14). The API key is never echoed back."""

    gateway_url: str
    gateway_api_key_set: bool
    gateway_enabled: bool
    ssl_verify: bool
    tls_warning: str | None = None
    # Populated only while the gateway is off, so the drawer can explain the
    # disabled dropdowns instead of looking broken.
    gateway_offline_reason: str | None = None
    models: dict[str, str]
    unconfigured_roles: list[str]
    graph_backend: str


class RuntimeSettingsPatch(BaseModel):
    """US-8: change gateway config and model routing without a restart."""

    gateway_url: str | None = None
    gateway_api_key: str | None = None
    # Flip the master switch without a restart, so a demo that starts offline
    # can be pointed at a live gateway mid-session.
    gateway_enabled: bool | None = None
    ssl_verify: bool | None = None
    # role -> alias. Only the roles present are touched; "" clears a role back
    # to unconfigured.
    models: dict[str, str] | None = None


class ModelCatalog(BaseModel):
    """Result of probing GET {gateway}/v1/models (FR-14)."""

    gateway_url: str
    models: list[str]
    embedding_models: list[str]
    probed_at: str


class SmokeRequest(BaseModel):
    prompt: str = Field(default="Reply with the single word: ready.", max_length=2000)


class SmokeResponse(BaseModel):
    """Stage 1 walking-skeleton probe: proves the full LLM path end to end."""

    reply: str
    model_role: str
