"""Boot-time environment validation (PRD FR-21).

Single source of truth for every tunable. Nothing else in the codebase reads
os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

# Fixed set of routing roles. The catalogue behind each one is discovered at
# runtime from the gateway; the roles themselves are a design decision.
MODEL_ROLES: tuple[str, ...] = ("triage", "digest", "reason", "embed")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LiteLLM gateway -----------------------------------------------------
    gateway_url: str = "http://localhost:4000"
    gateway_api_key: str = ""

    # --- Model aliases -------------------------------------------------------
    # Deliberately EMPTY by default: nothing is routed until the operator probes
    # the gateway catalogue and picks a model per role in the settings drawer.
    # A pre-populated guess that the gateway does not serve fails at the first
    # real call with an opaque upstream error, which is worse than an explicit
    # "not configured". MODEL_* in .env remains an escape hatch for unattended
    # runs; leave them unset for the UI-driven flow.
    model_triage: str = ""
    model_digest: str = ""
    model_reason: str = ""
    model_embed: str = ""

    # --- TLS (see PRD 7.2 for the trade-off) --------------------------------
    ssl_verify: bool = True

    # --- Server (unprivileged port, non-negotiable) -------------------------
    host: str = "127.0.0.1"
    port: int = 8787

    # --- Storage ------------------------------------------------------------
    data_dir: Path = REPO_ROOT / "backend" / "data"

    # --- Knowledge graph ----------------------------------------------------
    graph_backend: Literal["auto", "neo4j", "kuzu"] = "auto"
    neo4j_uri: str = ""
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # --- Observability (fire-and-forget, must never fail a request) ---------
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "adaptive-action-copilot"

    # --- Retries (PRD FR-22) ------------------------------------------------
    llm_max_attempts: int = 4
    llm_backoff_base_s: float = 1.0

    @field_validator("port")
    @classmethod
    def _unprivileged_port(cls, v: int) -> int:
        if v <= 1024:
            raise ValueError(
                f"port must be > 1024 (user-space execution, zero-admin constraint); got {v}"
            )
        return v

    @field_validator("gateway_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    # --- Derived ------------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def kuzu_dir(self) -> Path:
        return self.data_dir / "kuzu"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def openai_base_url(self) -> str:
        """LiteLLM exposes an OpenAI-compatible surface at /v1."""
        return self.gateway_url if self.gateway_url.endswith("/v1") else f"{self.gateway_url}/v1"

    @property
    def configured_models(self) -> dict[str, str]:
        """Alias per role. An empty string means "not chosen yet"."""
        return {role: getattr(self, f"model_{role}") for role in MODEL_ROLES}

    def set_model(self, role: str, alias: str) -> None:
        if role not in MODEL_ROLES:
            raise ValueError(f"unknown model role '{role}'; expected one of {list(MODEL_ROLES)}")
        setattr(self, f"model_{role}", alias.strip())

    @property
    def unconfigured_roles(self) -> list[str]:
        return [role for role, alias in self.configured_models.items() if not alias]

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.chroma_dir, self.kuzu_dir, self.upload_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
