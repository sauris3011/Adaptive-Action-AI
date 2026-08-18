"""The ONLY place a model client is constructed (PRD 5.7).

TLS policy, backoff retries, the prompt cache and the telemetry ledger all hang
off this module. Nothing else in the codebase imports a LangChain chat model.

LiteLLM is the gateway; LangChain is the client. model_provider="openai" because
the proxy speaks the OpenAI wire format - that is what keeps the "provider
agnostic" promise real rather than nominal.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.config import get_settings
from app.db.engine import connect, query_one
from app.llm import ledger
from app.llm.guard import CallClass, enforce
from app.logging_setup import get_logger
from app.schemas.grounding import GroundingContext
from app.tls import build_http_client

log = get_logger("llm.factory")

T = TypeVar("T", bound=BaseModel)

_TRANSIENT = ("429", "500", "502", "503", "504", "timeout", "timed out",
              "connection reset", "temporarily unavailable", "overloaded")


def _is_transient(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _TRANSIENT)


@lru_cache(maxsize=8)
def get_model(role: str) -> BaseChatModel:
    """Build (once per role) a chat model pointed at the LiteLLM gateway."""
    settings = get_settings()
    alias = settings.configured_models.get(role)
    if alias is None:
        raise KeyError(
            f"unknown model role '{role}'; expected one of {list(settings.configured_models)}"
        )
    return init_chat_model(
        model=alias,
        model_provider="openai",
        base_url=settings.openai_base_url,
        # The OpenAI client rejects an empty key outright; a placeholder keeps
        # the failure at the gateway where the error message is useful.
        api_key=settings.gateway_api_key or "sk-no-key-configured",
        temperature=0,
        http_client=build_http_client(),
        http_async_client=build_http_client(is_async=True),
    )


# --------------------------------------------------------------------------
# Prompt cache
# --------------------------------------------------------------------------

def _cache_key(model: str, messages: list[BaseMessage], schema_name: str) -> str:
    blob = json.dumps(
        [{"type": m.type, "content": m.content} for m in messages],
        sort_keys=True, default=str,
    )
    return hashlib.sha256(f"{model}|{schema_name}|{blob}".encode()).hexdigest()


def _cache_get(key: str) -> str | None:
    row = query_one("SELECT response FROM llm_cache WHERE cache_key = ?", (key,))
    if row is None:
        return None
    with connect() as conn:
        conn.execute("UPDATE llm_cache SET hits = hits + 1 WHERE cache_key = ?", (key,))
    return row["response"]


def _cache_put(key: str, model: str, response: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (cache_key, model, response, created_at, hits) "
            "VALUES (?,?,?,?,COALESCE((SELECT hits FROM llm_cache WHERE cache_key = ?),0))",
            (key, model, response, datetime.now(timezone.utc).isoformat(), key),
        )


def _usage(raw: Any) -> tuple[int, int]:
    meta = getattr(raw, "usage_metadata", None) or {}
    if meta:
        return int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))
    fallback = (getattr(raw, "response_metadata", None) or {}).get("token_usage", {})
    return int(fallback.get("prompt_tokens", 0)), int(fallback.get("completion_tokens", 0))


# --------------------------------------------------------------------------
# Invocation
# --------------------------------------------------------------------------

def invoke_structured(
    role: str,
    messages: list[BaseMessage],
    schema: type[T],
    *,
    call_class: CallClass,
    node: str,
    grounding: GroundingContext | None = None,
    exemption_reason: str | None = None,
    run_id: str | None = None,
    use_cache: bool = True,
) -> T:
    """Every LLM response entering application logic passes through here."""
    settings = get_settings()
    reason = enforce(call_class, grounding, node=node, exemption_reason=exemption_reason)
    alias = settings.configured_models[role]
    key = _cache_key(alias, messages, schema.__name__)

    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            ledger.record(model=alias, call_class=call_class.value, cache_hit=True,
                          run_id=run_id, node=node, exemption_reason=reason)
            return schema.model_validate_json(cached)

    model = get_model(role).with_structured_output(schema, include_raw=True)
    started = time.perf_counter()
    last_exc: BaseException | None = None

    with ledger.InFlight():
        for attempt in range(1, settings.llm_max_attempts + 1):
            try:
                result = model.invoke(messages)
                parsed, raw = result.get("parsed"), result.get("raw")
                if parsed is None:
                    raise ValueError(
                        f"structured output failed validation: {result.get('parsing_error')}"
                    )

                elapsed = int((time.perf_counter() - started) * 1000)
                prompt_tokens, completion_tokens = _usage(raw)
                ledger.record(model=alias, call_class=call_class.value,
                              prompt_tokens=prompt_tokens,
                              completion_tokens=completion_tokens,
                              latency_ms=elapsed, run_id=run_id, node=node,
                              exemption_reason=reason)
                if use_cache:
                    _cache_put(key, alias, parsed.model_dump_json())
                return parsed

            except Exception as exc:  # noqa: BLE001 - classified by _is_transient
                last_exc = exc
                if attempt >= settings.llm_max_attempts or not _is_transient(exc):
                    break
                backoff = settings.llm_backoff_base_s * (2 ** (attempt - 1))
                log.warning("llm_retry", node=node, attempt=attempt,
                            backoff_s=backoff, error=str(exc))
                time.sleep(backoff)

    elapsed = int((time.perf_counter() - started) * 1000)
    ledger.record(model=alias, call_class=call_class.value, latency_ms=elapsed,
                  run_id=run_id, node=node, exemption_reason=reason, error=str(last_exc))
    raise RuntimeError(f"LLM call failed at node '{node}': {last_exc}") from last_exc


def invoke_text(
    role: str,
    messages: list[BaseMessage],
    *,
    call_class: CallClass,
    node: str,
    grounding: GroundingContext | None = None,
    exemption_reason: str | None = None,
    run_id: str | None = None,
) -> str:
    """Free-text escape hatch. Not for anything entering application logic."""
    settings = get_settings()
    reason = enforce(call_class, grounding, node=node, exemption_reason=exemption_reason)
    alias = settings.configured_models[role]
    started = time.perf_counter()

    with ledger.InFlight():
        try:
            raw = get_model(role).invoke(messages)
        except Exception as exc:
            ledger.record(model=alias, call_class=call_class.value,
                          latency_ms=int((time.perf_counter() - started) * 1000),
                          run_id=run_id, node=node, exemption_reason=reason,
                          error=str(exc))
            raise

    prompt_tokens, completion_tokens = _usage(raw)
    ledger.record(model=alias, call_class=call_class.value,
                  prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                  latency_ms=int((time.perf_counter() - started) * 1000),
                  run_id=run_id, node=node, exemption_reason=reason)
    return str(raw.content)
