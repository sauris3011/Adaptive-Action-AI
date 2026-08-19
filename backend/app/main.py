"""FastAPI application assembly.

Boot order matters: validate config, then storage, then graph backend, then
serve. Anything that can fail should fail here with a clear message rather than
inside the first user request.
"""

from __future__ import annotations

import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (routes_copilot, routes_core_banking, routes_grounding,
                     routes_settings, routes_telemetry)
from app.config import get_settings
from app.db.models import migrate
from app.graph.base import active_backend, close_store, select_backend
from app.logging_setup import configure_logging, get_logger
from app.schemas.api import HealthResponse
from app.tls import tls_warning

VERSION = "0.1.0"
log = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    settings.ensure_dirs()
    migrate()

    warning = tls_warning()
    if warning:
        log.warning("tls_verification_disabled", detail=warning)

    try:
        select_backend()
    except Exception as exc:  # noqa: BLE001
        log.error("graph_backend_unavailable", error=str(exc))
        raise

    log.info("startup_complete", version=VERSION, port=settings.port,
             graph_backend=active_backend(), ssl_verify=settings.ssl_verify)
    yield
    # Graceful shutdown (FR-23). Uvicorn already traps SIGINT/SIGTERM and runs
    # this teardown; SQLite connections are per-operation, but the graph driver
    # is a long-lived singleton and must be closed explicitly.
    close_store()
    log.info("shutdown_complete")


app = FastAPI(
    title="Adaptive Knowledge-to-Action Copilot",
    version=VERSION,
    lifespan=lifespan,
)

# The Vite dev server is a separate origin. The UI never calls the LLM gateway
# directly - it only ever talks to this backend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_telemetry.router)
app.include_router(routes_settings.router)
app.include_router(routes_copilot.router)
app.include_router(routes_grounding.router)
# Mounted in-process: the action workflow calls this over loopback (FR-26).
app.include_router(routes_core_banking.router)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=VERSION,
        graph_backend=active_backend(),
        tls_warning=tls_warning(),
    )
