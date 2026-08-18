"""Structured JSON logging with automatic secret/PII redaction (PRD FR-24).

Every LLM call, graph query and agent action logs latency, tokens, model and
cache hit/miss through this configuration. Redaction runs as a processor so it
cannot be forgotten at a call site.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

REDACTED = "<redacted>"

# Keys whose values are never safe to emit.
_SECRET_KEY_RE = re.compile(
    r"(api_key|apikey|password|passwd|secret|token|authorization|auth|credential|bearer)",
    re.IGNORECASE,
)

# Value-level patterns. Card number first: this is a banking domain and a PAN
# leaking into a log is the worst single failure available to us.
_VALUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "<card-redacted>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email-redacted>"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"), "<key-redacted>"),
]

_MAX_VALUE_LEN = 2000


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pattern, replacement in _VALUE_PATTERNS:
            out = pattern.sub(replacement, out)
        if len(out) > _MAX_VALUE_LEN:
            out = out[:_MAX_VALUE_LEN] + f"...<truncated {len(out) - _MAX_VALUE_LEN} chars>"
        return out
    if isinstance(value, dict):
        return _scrub_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


def _scrub_mapping(data: dict[Any, Any]) -> dict[Any, Any]:
    out: dict[Any, Any] = {}
    for key, value in data.items():
        if isinstance(key, str) and _SECRET_KEY_RE.search(key):
            out[key] = REDACTED
        else:
            out[key] = _scrub_value(value)
    return out


def redaction_processor(_logger: Any, _name: str, event_dict: dict) -> dict:
    return _scrub_mapping(event_dict)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redaction_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "copilot"):
    return structlog.get_logger(name)
