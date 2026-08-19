# Adaptive Knowledge-to-Action Copilot

A copilot that grounds itself in **both** unstructured policy and structured entity state,
explicitly reconciles conflicting sources under a declared precedence order, and — behind a
mandatory human approval gate — completes the work end to end.

Reference vertical: **retail banking card disputes**.

- **[prd.md](prd.md)** — the source of truth. Any code that contradicts it is a defect in the code.
- **[problem_statement.md](problem_statement.md)** — the challenge this answers.
- **[Agentic-development-master-prompt-revised.md](Agentic-development-master-prompt-revised.md)** — governing constraints.

## Design thesis

**Reconciliation is the product.** A copilot that answers from documents is a commodity. One that
says *"these two sources disagree, here is which one governs and why"* is not. Retrieval, the graph,
and the action workflow are supporting capabilities.

The corpus carries three deliberate contradictions (PRD §4). The sharpest is **C3**: a fraud flag
that exists only in the transaction record, not in any document — a documents-only RAG system cannot
resolve it at all.

## Quick start

```bash
cp .env.example .env
```

Fill in `GATEWAY_URL` and `GATEWAY_API_KEY`, then:

```bash
./startup.sh
```

On Windows, `startup.bat`. Backend on `:8787`, UI on `:5173`. Both scripts run pre-flight first and
refuse to start if it fails.

Backend only:

```bash
./startup.sh --no-ui
```

## Pre-flight

```bash
.venv/Scripts/python.exe backend/scripts/preflight.py
```

Verifies venv, Python ≥3.11, Node ≥20, port 8787 free, data dir writable, gateway reachable, **every
configured model alias present in the gateway's live `/v1/models`**, and Neo4j reachable-or-fallback.
Fails fast naming the exact missing item.

The model-alias check matters: a wrong ID fails at runtime, mid-demo. Pre-flight prints what the
gateway actually offers.

## Architecture

| Concern | Choice | Why |
|---|---|---|
| Agent runtime | LangGraph, single state machine | Same ecosystem as the mandated `init_chat_model`; `SqliteSaver` gives durable approval gates free |
| LLM routing | LangChain → LiteLLM proxy (`model_provider="openai"`) | LiteLLM is the gateway, LangChain the only client. The UI never calls the gateway |
| Vector | ChromaDB, local persistent | No daemon |
| Graph | Neo4j Aura primary, embedded Kùzu fallback | Corporate proxy is the top demo-day risk; fallback is automatic and logged |
| Relational | SQLite | App state, checkpoints, telemetry ledger, cache, cases |
| Telemetry | Own SQLite ledger | An always-visible header must not depend on a SaaS round trip through a TLS-intercepting proxy |

### Two decisions worth knowing before reading the code

**1. Grounding is enforced by call class, not blanket injection.** The master prompt asks for
grounding on "every LLM call". Literally applied that injects policy chunks into routing calls for
no benefit. Instead every call is tagged `GROUNDED` (hard-fails on empty context) or `UTILITY`
(exempt, but the reason is logged every time). One enforcement point:
[guard.py](backend/app/llm/guard.py).

**2. Precedence is deterministic, not a model judgement.** Every chunk carries its tier
(regulation > network rules > bank policy > product terms) as ingestion metadata. The LLM identifies
contradictions; the ladder resolves them. That makes conflict resolution testable.

### Layout

```
backend/app/     config, tls, logging_setup, main
  llm/           factory (sole model construction site), embeddings, guard, ledger, pricing
  schemas/       grounding, corpus, api
  rag/           loaders (MIME registry), chunker, store (Chroma), ingest, retrieve
  graph/         base (protocol + selection), schema, kuzu_store, neo4j_store, traverse, extract
  db/            engine, models, records (entity state, incl. the fraud flag)
  api/           routes_{telemetry,settings,copilot,grounding}
backend/domain/  banking/{corpus/*.md, records.json} - the domain pack: data, not code
backend/scripts/ preflight, seed_data
frontend/src/    components/{Header,SettingsDrawer,Grounding,ui}, routes, lib, styles/tokens.css
```

300–400 LOC ceiling per file. Every colour resolves through a token in
[tokens.css](frontend/src/styles/tokens.css) — no component hardcodes one, which is what makes the
theme toggle a single switch rather than a per-component audit.

## Security note

`SSL_VERIFY=false` disables certificate verification for the intercepting corporate proxy. **With it
off, the app cannot distinguish that proxy from a hostile man-in-the-middle** — prompts, retrieved
context and responses are exposed to anyone able to intercept. Acceptable only because this is a
local prototype on synthetic data with no production credentials. The production fix is to trust the
corporate root CA via `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`, not to disable verification. See
PRD §7.2.

## Status

| Stage | State |
|---|---|
| 0 — PRD | Done |
| 1 — Walking skeleton | Done: config, TLS, logging, ledger, guard, factory, pre-flight, startup scripts, UI shell with header monitor, theme toggle, settings drawer |
| 2 — Grounding | Done: domain pack with C1–C3, MIME-keyed ingest, Chroma, Kùzu + Neo4j stores, relational facts, hybrid fan-out, grounding panel with force graph and upload |
| 3 — LangGraph reasoning pipeline | Not started |
| 4 — Action workflow + approval gate | Not started |
| 5 — Eval, KPIs, A2A, docs | Not started |

The Copilot page currently ships a gateway connectivity probe, not the dispute workflow. That lands
in Stage 3.

### Seeding

```bash
.venv/Scripts/python.exe backend/scripts/seed_data.py --reset
```

Prints document, chunk, node and relationship counts read back from the stores — they must match the
grounding panel (acceptance criterion 3). `startup.sh` / `startup.bat` run it with `--if-empty`, so a
normal restart does not pay the embedding cost.

Kùzu is a **single-writer** embedded store: the running backend holds the lock, so the CLI seeder
cannot run alongside it. Re-seed a live instance with `POST /api/grounding/reseed` (the "Re-seed
domain pack" button) instead of stopping the server.

### Two gaps against PRD §5.2, found by probing the live gateway

Both are stated rather than worked around silently:

- **No embedding model.** The gateway serves chat models only. Embeddings fall back to Chroma's
  bundled ONNX MiniLM (local, zero-daemon, zero-admin) — still the same
  [embeddings.py](backend/app/llm/embeddings.py) construction site, and the gateway path activates
  the moment an `embed` alias exists. A hashed lexical embedder is the last resort and reports
  itself as degraded in the panel and the logs.
- **No pro-tier model.** The catalogue is flash and flash-lite only, so the `reason` role — which
  PRD §5.2 assigns to pro for `reconcile` and `recommend` — has no pro option to select. This
  becomes material in Stage 3.
