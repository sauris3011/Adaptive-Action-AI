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

### Running without a gateway

`GATEWAY_ENABLED=false` in `.env` turns off all outbound model traffic. Retrieval, the knowledge
graph, the relational store, KPIs and the mock core-banking API run exactly as they do online;
embeddings are served by Chroma's bundled MiniLM (`local:all-MiniLM-L6-v2`, 384d), which is a real
semantic embedder, not the degraded hashing fallback. The reasoning nodes are the only thing that
needs a gateway, and while it is off they answer `409` with the reason rather than failing four
backoff retries deep in an unreachable host. The eval harness drives the same reasoning nodes, so
`run_eval.py` needs a gateway too.

Turn it back on by setting `GATEWAY_ENABLED=true` (and pointing `GATEWAY_URL` at a live proxy), or
with the **Use the LLM gateway** toggle in Settings, which takes effect without a restart.

## Pre-flight

```bash
.venv/Scripts/python.exe backend/scripts/preflight.py
```

Verifies venv, Python ≥3.11, Node ≥20, port 8787 free, data dir writable, gateway reachable, **every
configured model alias present in the gateway's live `/v1/models`**, and Neo4j reachable-or-fallback.
Fails fast naming the exact missing item. With `GATEWAY_ENABLED=false` the gateway and model-alias
checks are skipped and reported as such, rather than timing out against a host that will not be
called.

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
  graph/         base (protocol + selection), schema, kuzu_store, neo4j_store, traverse,
                 extract (projection from the record), ask (five-query surface resolver)
  db/            engine, models, records (entity state + disputes, incl. the fraud flag),
                 lookup (transaction search + derived signals), cases, trace
  agents/        graph (topology + interrupt), nodes, prompts, actions, state
  tools/         core_banking (mock system of engagement)
  api/           routes_{telemetry,settings,copilot,grounding,records,core_banking,kpi,a2a}
backend/domain/  banking/{corpus/*.md, records.json} - the domain pack: data, not code
backend/scripts/ preflight, seed_data, run_eval, backend_drill
frontend/src/    components/{Header,SettingsDrawer,Grounding,Copilot,Transactions,ui}, routes,
                 lib/{api,schemas,schemas.records}, styles/tokens.css
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
| 3 — LangGraph reasoning pipeline | Done: triage/retrieve/reconcile/recommend, structured output, SqliteSaver checkpoints, run trace, conflict banner and recommendation UI |
| 4 — Action workflow + approval gate | Done: durable interrupt, mock core-banking router, action mapping, approve/reject with recorded outcomes, audit case view |
| 5 — Eval, KPIs, A2A | Done: 20-case labelled eval with KPI JSON, KPI strip, A2A conformance slice, graph-backend drill, persisted model routing |
| 6 — Record screens | Done: transaction look-up over the system of record, plain-language graph Q&A on the five-query surface, dispute write-back into the record and the graph |

The Copilot page runs the full dispute workflow end to end: recommendation, approval gate, action
execution against the mock core-banking API, and a recorded outcome on both paths.

### Opening a dispute writes to the record

Stage 6's look-up screen made a gap visible that Stage 4 had left: raising a dispute produced a
checkpoint, a trace and — after approval — a case row, but nothing the system reads back. Prior
dispute history is retrieved from the graph, and `Dispute` nodes only ever came from `records.json`
at seed time, so a dispute raised two minutes ago was invisible to the next run.

An `open_case` node now sits between `recommend` and the interrupt. It writes the intake to
`dispute_history` and projects it into the graph, and `record` closes the same row when a decision
lands. This is not a breach of the approval gate: it moves no money and calls no core-banking
endpoint, and BDP-2.1 makes intake itself the moment a case opens. It runs *after* `retrieve`, so
the dispute being raised does not appear in its own prior-dispute evidence.

Two things follow from having the state at all. The look-up screen carries a `DISPUTED` signal and
refuses a second intake on a transaction that already has an open case, offering the pending run
instead — previously the only route back to a parked approval was to raise the dispute again.
And `issue_provisional_credit` now refuses a second credit against an already-credited transaction:
per-`run_id` idempotency cannot see two runs on one transaction, which is exactly the shape a
double intake takes.

SQLite is the record and the graph is a projection of it, so `extract_records` reads disputes from
`dispute_history` rather than from the fixture. A re-seed without `--reset` therefore keeps disputes
raised at runtime, and `backend_drill.py` derives its expected `Dispute` count from the same place
rather than from the fixture's length.

### The approval gate

The graph is compiled with `interrupt_before=["gate"]`. There is no code path from `recommend` to
`act` that does not pass through a human decision written into the checkpoint (FR-6). The gate node
is deliberately empty — the moment it decides anything, the human gate becomes advisory.

Because the checkpoint is on disk, a run survives a full backend restart: kill the process mid-gate,
restart it, and the pending run is still approvable from its recovered state. Verified, not assumed.

| Path | Result |
|---|---|
| Approve | 3 × HTTP 200 from the mock API, case row with approver and timestamp |
| Reject | zero effects, outcome and reason still recorded (FR-8) |
| Double-approve | 409, no second credit — idempotent by `run_id` |
| Over agent limit as agent | 403 citing BDP-3.4; succeeds as Team Lead |
| Fraud routing approved | fraud-ops case only — no credit, no notice, honouring FSP-1.2 and FSP-5.1 |

The action mapping is deterministic ([actions.py](backend/app/agents/actions.py)). The model chose
the action; it does not also choose which endpoints get called with what payload. Policy decisions
that move money belong in code an auditor can read, not in a prompt.

### Bounded schema repair

PRD §5.3 requires one repair retry on a validation failure, then a typed error. Stage 3 shipped
without it — the factory only retried *transient* errors, so a model response that broke a field
constraint failed the whole run. A Stage 4 test hit exactly that (a 601-character
`resolution_basis`), which is how it surfaced.

[factory.py](backend/app/llm/factory.py) now feeds the validator's own message back once and asks
for the same conclusion reshaped to fit. Verified both ways: it repairs a satisfiable violation, and
on an unsatisfiable schema it stops after one attempt and raises `SchemaValidationError` — never a
silent fallback to free text.

### Conflict resolution, measured

All three engineered conflicts resolve correctly against the live gateway (`gemini-3.7-flash` on the
`reason` role):

| Conflict | Expected | Produced | Governing |
|---|---|---|---|
| C1 credit timing | 2 business days | 2 business days | PCT-7.1 over BDP-4.2 and REG-E-3 |
| C2 merchant contact | not a true conflict | flagged **apparent** only, both routes explained | CNR-11.4 (chargeback) vs GRS-2.3 (goodwill) |
| C3 fraud routing | route to Fraud Ops | `route_to_fraud_ops` | FSP-1.2 over BDP-2.1, from the record |

Latency 11–16s uncached, well inside the 90s p95 budget.

### Why retrieval is two-phase

C3 exposed a real architectural gap, not a prompt problem. The retrieval query is written by `triage`
from the cardholder's words — but the fact that decides C3, the fraud-engine flag, exists **only in
the transaction record**. Nothing the cardholder says can pull FSP-1.2 into context, so the first
implementation resolved C3 wrongly while reasoning impeccably over evidence that was missing the
governing clause.

The fix gives the record a vote in what gets retrieved: declarative triggers
([triggers.py](backend/app/rag/triggers.py)) map record fields to supplementary policy queries. They
are deterministic — no model decides this — and they live in the domain pack, so a new vertical
configures its own rather than editing code.

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


## Eval and KPIs

```bash
python backend/scripts/run_eval.py
```

Twenty labelled cases - nine dispute-intake, eleven policy questions, five exercising the engineered
conflicts. Exit code is 0 only when every PRD §9.1 and §9.2 target is met, so it is a gate rather
than a report. Stop the backend first: Kùzu is single-writer.

Latest run, cold start, against `gemini-3.7-flash` on the `reason` role:

| KPI | Target | Measured |
|---|---|---|
| Task completion time | ≤90s p95 | **19.9s** |
| Automation rate | ≥60% | **100%** |
| Resolution quality | ≥85% | **100%** |
| Citation presence / precision | 100% / ≥90% | **100% / 100%** |
| Conflict detection recall (C1–C3) | 100% | **100%** |
| Compliance adherence | 100% | **100%** |
| Cache hit ratio | ≥30% | **100%** (repeat pass) |
| Unhandled exceptions | 0 | **0** |

20/20 cases pass every scored dimension. 120 LLM calls, ~110k tokens, $0.10 per full run.

### Three things about how this is measured

**The scored pass runs cold.** The prompt cache persists across runs, so a second eval replays the
first and reports a p95 of two seconds at zero cost - numbers that describe the cache, not the
system. `run_eval.py` clears the cache first and measures the cache on a separate repeat pass. An
earlier version did not, and reported exactly those meaningless numbers.

**Scoring contains no model.** Every judgement is a set membership test or a substring match against
a label derived from the corpus. An eval that asks an LLM whether the LLM was right measures
agreement, not correctness.

**Labels were corrected twice, and the corrections are recorded** in `_label_corrections` in
[eval_cases.json](backend/domain/banking/eval_cases.json) with reasons. Both were genuine label
defects, not accommodations: one conflated "highest tier" with "governs this request", and one
required a deadline of fraud-routed cases where FSP-1.2 transfers ownership. The second was found
because successive runs named *opposite* sides of the C2 pair as governing while classifying it
correctly as apparent both times - so the label was pinning something the metric does not test.

Two model defects the eval caught were fixed in the prompt and schema rather than in the labels:
`governing_clause` could name a clause unrelated to the recommended action, and `deadline` could
answer "none applicable" to a question that was itself about a filing window. Both field contracts
were under-specified.

## Graph backend drill

```bash
python backend/scripts/backend_drill.py
```

27 checks: fallback selection plus the full five-query surface compared against values derived from
the fixture. Passes on Kùzu. `GRAPH_BACKEND=neo4j python backend/scripts/backend_drill.py` runs the
same checks against Aura and **exits 2 with a clear message when credentials are absent**, rather
than passing on one backend and implying it covered two.

**Honest status:** the Neo4j leg has never been executed - there are no Aura credentials in this
environment. The implementation exists and shares the contract, but PRD §9.2's "100% of eval cases
pass on both graph backends" is unverified on the second backend.

## A2A conformance slice

```bash
curl http://127.0.0.1:8787/.well-known/agent.json
```

An agent card and one JSON-RPC method (`message/send`). The card states its own limitations rather
than implying conformance it does not have. `message/send` runs the same graph the UI does and
returns A2A state `input-required`: an agent calling in cannot execute a monetary action, because
the interrupt is a property of the graph rather than of the HTTP layer in front of it.
