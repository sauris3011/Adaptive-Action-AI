"""Cost estimation for the header monitor (PRD FR-13).

Rates are USD per 1M tokens and are ESTIMATES. FR-13 requires a fallback when a
model is unpriced, so an unknown model resolves to FALLBACK rather than showing
zero cost - silently reporting 0.00 for an unrecognised model would be worse
than reporting an approximation, because it reads as "free" rather than
"unknown".

Override without touching code by dropping a JSON file at
backend/data/pricing.json:  {"model-alias": {"in": 0.15, "out": 0.60}}
"""

from __future__ import annotations

import json
from functools import lru_cache

from app.config import get_settings

# Matched by longest substring, so "gemini/gemini-2.5-pro" resolves via
# "gemini-2.5-pro" without needing every gateway prefix enumerated.
_RATES: dict[str, dict[str, float]] = {
    "gemini-2.5-pro": {"in": 1.25, "out": 10.00},
    "gemini-2.5-flash-lite": {"in": 0.10, "out": 0.40},
    "gemini-2.5-flash": {"in": 0.30, "out": 2.50},
    "gemini-3-pro": {"in": 1.25, "out": 10.00},
    "gemini-3-flash": {"in": 0.30, "out": 2.50},
    "text-embedding": {"in": 0.02, "out": 0.00},
}

FALLBACK = {"in": 0.50, "out": 1.50}


@lru_cache(maxsize=1)
def _table() -> dict[str, dict[str, float]]:
    table = dict(_RATES)
    override = get_settings().data_dir / "pricing.json"
    if override.exists():
        try:
            table.update(json.loads(override.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # a malformed override must never break a request
    return table


def rates_for(model: str) -> tuple[dict[str, float], bool]:
    """Return (rates, is_known). is_known=False means FALLBACK was used."""
    table = _table()
    key = model.lower()
    best: str | None = None
    for candidate in table:
        if candidate in key and (best is None or len(candidate) > len(best)):
            best = candidate
    if best is None:
        return FALLBACK, False
    return table[best], True


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates, _ = rates_for(model)
    return (prompt_tokens * rates["in"] + completion_tokens * rates["out"]) / 1_000_000
