# Product Requirements Document

**Product:** Adaptive Knowledge-to-Action Copilot
**Reference implementation vertical:** Retail banking — card transaction disputes
**Status:** Draft for approval (Phase 2, Deliverable 1)
**Governing spec:** `Agentic-development-master-prompt-revised.md`
**Source challenge:** `problem_statement.md` (Challenge 1)

> Once approved, this document is the strict reference for all subsequent phases. Any code, API,
> schema, or file layout that contradicts this PRD is a defect in the code, not in the PRD.

---

## 1. Product Vision & Problem Statement

### 1.1 Problem

Enterprises hold the knowledge needed to resolve work, but it is scattered across policy documents,
regulatory summaries, SOPs, product terms, transactional systems, and historical case records. Three
failures follow:

1. **Retrieval is not reconciliation.** Search returns the passage that matches the words, not the
   clause that actually governs. When two sources disagree, conventional RAG silently picks whichever
   chunk ranked higher and presents it with full confidence.
2. **Documents alone are not enough.** The correct answer often depends on live entity state — a
   fraud flag on the transaction, a customer's product tier, a merchant's dispute history — that
   exists in systems of record, not in prose.
3. **Answers are not outcomes.** Even a correct answer leaves a human to open four systems and
   perform the action manually.

### 1.2 Vision

A copilot that understands a work goal, grounds itself in **both** unstructured policy and
structured entity state, **explicitly reconciles conflicting sources under a declared precedence
order**, explains its recommendation with citations and a confidence score, and — behind a mandatory
human approval gate — completes the work end to end.

### 1.3 Why banking disputes is the reference vertical

It is the smallest domain that exercises every capability the challenge asks for at once: genuinely
conflicting sources, multi-hop entity reasoning, a regulated deadline, a monetary action that must
not be automated without oversight, and KPIs that a business would actually track.

### 1.4 Design thesis

**Reconciliation is the product.** Retrieval, the graph, and the action workflow are supporting
capabilities. A demo that merely answers questions from documents is a commodity; a demo that says
*"these two sources disagree, here is which one governs and why"* is not.

---

## 2. Target Audience & Personas

| Persona | Role | Goal | Today's friction |
|---|---|---|---|
| **Priya** — Dispute Resolution Agent *(primary user)* | Contact-centre agent, 40–60 disputes/day | Decide whether a disputed transaction qualifies for provisional credit, under which rule, by what deadline | Switches between ~4 systems; reads a 60-page policy PDF; escalates when unsure |
| **Marcus** — Disputes Team Lead *(approver)* | Approves credits above agent authority | Approve or reject quickly with confidence | Gets a recommendation with no visible reasoning or governing clause |
| **Aisha** — Compliance & Risk Analyst *(assurance)* | Audits decisions after the fact | Reconstruct what was retrieved, which clause governed, who approved, when | Audit trail is partial and lives across systems |
| **Dev** — Platform Engineer *(secondary)* | Configures the copilot for a new vertical | Swap the domain pack without forking the codebase | N/A — new capability |

Priya is the persona the UI is optimised for. Marcus is the reason the approval gate exists. Aisha is
the reason every decision writes an immutable trace.

---

## 3. User Stories & Core Workflows

### 3.1 Flagship workflow — Dispute intake to provisional credit *(end-to-end action workflow)*

**US-1.** As Priya, I submit a cardholder's dispute in natural language and receive a grounded,
explainable recommendation in under 90 seconds, so that I do not have to read policy myself.

**US-2.** As Priya, when sources disagree I am shown *that they disagree*, which one governs, and
why — so that I am not silently given the wrong answer.

**US-3.** As Marcus, no monetary action executes until I explicitly approve it, and I see the
reasoning, citations, and confidence before I do.

**US-4.** As Aisha, every run records the retrieved context, the governing clause, the approver, and
the outcome.

**Execution narrative:**

| # | Step | System behaviour |
|---|---|---|
| 1 | Priya submits the dispute | `triage` extracts intent + entities (customer, transaction, dispute reason) into a validated schema |
| 2 | — | `retrieve` fans out in parallel: Chroma (policy passages), graph (customer/merchant/transaction neighbourhood), SQLite (transaction facts, incl. **fraud flag**) |
| 3 | — | `reconcile` detects contradictions across sources and ranks them by the precedence ladder (5.4) |
| 4 | — | `recommend` emits action, rationale, citations, deadline, confidence — strictly validated |
| 5 | Priya reviews | UI shows recommendation, conflict banner, citations, confidence, and the exact clauses |
| 6 | Marcus approves / rejects | Graph is **paused at an interrupt**; nothing has executed yet |
| 7 | On approve | Tools call the mock core-banking API: provisional credit, dispute case, customer notice |
| 8 | Always | Outcome, KPIs, and full trace written to SQLite |

**Rejection path:** no side effect on the mock API; the rejection and its reason are still recorded.

### 3.2 Supporting workflows

**US-5 (Q&A).** As Priya, I ask a policy question and get a cited answer without starting a case.
**US-6 (Grounding management).** As Dev, I upload a document and see it embedded and extracted into
the graph, with counts updating.
**US-7 (Observability).** As any user, I see live LLM call count, token usage, and estimated cost.
**US-8 (Configuration).** As Dev, I change the gateway URL/key and the SSL flag without a restart.

---

## 4. The engineered conflicts *(demo payload — normative)*

The synthetic corpus **must** contain these three contradictions. They are the evidence for 1.4 and
the eval set is built on them.

**C1 — Provisional credit timing.**
`BDP-4.2` (Bank Dispute Policy): provisional credit within **10 business days**.
`PCT-7.1` (Premium Card T&Cs): within **2 business days** for Signature cardholders.
`REG-E-3` (Regulatory summary): 10 business days is a **maximum**, extendable to 20 for new accounts.
→ Correct outcome for a Signature cardholder: **2 business days.** The regulation sets a ceiling, not
a target; the product term is a stricter promise in the customer's favour and therefore binds.
*Naive RAG returns whichever chunk ranks higher.*

**C2 — Merchant contact requirement.**
`GRS-2.3` (Goodwill Refund SOP): refunds under **50 USD** auto-approve with no merchant contact.
`CNR-11.4` (Card Network Rules): "goods not received" chargebacks require prior merchant contact.
→ Correct outcome: **not a true conflict** — goodwill refund and chargeback are different
instruments. The copilot must say so and offer the goodwill route as immediately available while
noting the chargeback route still requires merchant contact.
*This tests reconciliation judgement, not retrieval.*

**C3 — Fraud routing overrides dispute intake.**
`FSP-1.2` (Fraud SOP): any transaction carrying a fraud-engine flag routes to Fraud Ops.
`BDP-2.1` (Bank Dispute Policy): cardholder-reported unauthorised transactions open a dispute case.
→ Correct outcome: **route to Fraud Ops.** The fraud flag exists **only in the transaction record**,
not in any document.
*This is the conflict that proves hybrid grounding earns its cost — a documents-only system cannot
resolve it at all.*

---

## 5. AI & System Architecture

### 5.1 Agent topology

A **single LangGraph state machine** — linear, with one parallel fan-out and one interrupt. A
multi-agent crew was considered and rejected: per master prompt section 4 ("prefer the simplest
architecture"), role-play agents would add latency, token cost, and failure modes without adding
capability, because this workflow has no genuinely independent concurrent goals.

```
triage --> retrieve (parallel: vector | graph | relational) --> reconcile --> recommend
                                                                                 |
                                                         interrupt() <-----------+
                                                               |
                                                   approve --> act --> record
                                                   reject  --> record
```

Durable state via `SqliteSaver`, which also satisfies the agent-run-metadata requirement. The
approval gate survives a page reload because the checkpoint is on disk, not in memory.

### 5.2 Model mapping

| Node / role | Tier | Rationale |
|---|---|---|
| `triage`, extraction, routing | flash-lite | High volume, schema-constrained, low reasoning demand |
| tool-output digest | flash | Summarisation only |
| `reconcile`, `recommend` | pro | The only steps requiring genuine multi-source reasoning |
| Embeddings | gateway embedding model | Via LangChain integration, same proxy, same TLS config |

**Model IDs are unverified and must be validated at pre-flight** against the gateway's live
`/v1/models`. A wrong ID fails at runtime; pre-flight must fail fast and print what the gateway
actually offers.

### 5.3 Structured output enforcement

Every LLM response entering application logic is a Pydantic model, requested via LangChain's
structured-output binding and validated before use. A validation failure triggers one bounded repair
retry, then a typed error surfaced to the UI — never a silent fallback to free text.

### 5.4 Precedence ladder *(normative — drives `reconcile`)*

1. **Regulatory requirement** — hard floor/ceiling, cannot be violated
2. **Card network rules** — contractual with the scheme
3. **Bank policy & SOP** — internal
4. **Product terms & conditions** — contractual with the customer

**Override rule:** where a lower tier is *more favourable to the customer* and breaches no higher
tier, the more favourable term binds. (This is what makes C1 resolvable.)

Every source chunk carries its tier as metadata at ingestion, so precedence is a **deterministic
property of the corpus, not an LLM judgement call.** The model identifies the contradiction; the
ladder resolves it.

### 5.5 Hybrid grounding

- **Vector (ChromaDB, local persistent):** policy passages, chunked with tier + clause-ID metadata.
- **Graph (Neo4j Aura primary, embedded Kuzu fallback):** Customer-HOLDS-Account-MADE-Transaction-AT-Merchant,
  Customer-RAISED-Dispute, Policy-SUPERSEDES/REFERENCES-Policy. Free-tier ceiling (50k nodes /
  175k relationships) is roughly two orders of magnitude above the seed corpus; no partitioning required.
- **Relational (SQLite):** authoritative transaction facts including the fraud flag.

`GraphStore` is a Protocol with a **fixed five-query surface** — `customer_dispute_history`,
`merchant_risk_profile`, `policy_dependencies`, `transaction_context`, `neighborhood(entity, hops)`
— deliberately *not* a Cypher passthrough, because Kuzu's Cypher dialect diverges from Neo4j's and a
passthrough would make the second backend unaffordable.

### 5.6 Grounding enforcement *(resolves master prompt section 5)*

Section 5 requires grounding on "*every* LLM call." Applied literally this injects policy chunks and
graph triples into routing and extraction calls, inflating cost and latency with no benefit. **Intent
is interpreted as: no ungrounded answers.**

Every call is tagged at its call site:

- **`GROUNDED`** — hard-fails if `GroundingContext` is empty. All answer- and
  recommendation-generating calls.
- **`UTILITY`** — exempt, but the exemption reason is **logged on every call**, so the rule stays
  auditable rather than quietly eroded.

Enforced in one place (`app/llm/guard.py`). Bypassing it requires editing that file.

### 5.7 LLM routing

LangChain `init_chat_model(model=<gateway alias>, model_provider="openai", base_url=<litellm proxy>)`.
`model_provider="openai"` because the LiteLLM proxy speaks the OpenAI wire format — this is what
keeps the "provider agnostic" promise real rather than nominal. **LiteLLM is the gateway; LangChain
is the only client.** The UI never calls the gateway directly.

`app/llm/factory.py` is the sole construction site for model clients. TLS config, exponential-backoff
retries (429/502/503), the prompt cache, and the telemetry ledger write all hang off it.

### 5.8 Telemetry — deliberate design decision

The header monitor is fed from **our own SQLite ledger**, written by the wrapper on every call —
**not** from a round trip to LiteLLM `/spend`, and **not** from LangSmith. Rationale: behind a
TLS-intercepting corporate proxy, an always-visible UI element that depends on a SaaS round trip is
the single most likely thing to fail during a live demo.

LangSmith tracing is fire-and-forget, default off, one env var to enable, and **must never block or
fail a request.**

---

## 6. Functional Requirements

### 6.1 Copilot core

| ID | Requirement |
|---|---|
| FR-1 | Accept a natural-language work request and classify intent into a validated schema |
| FR-2 | Retrieve from vector, graph, and relational sources in parallel |
| FR-3 | Detect contradictions across retrieved sources and resolve them by the 5.4 ladder |
| FR-4 | Emit a recommendation with action, rationale, citations, applicable deadline, and confidence |
| FR-5 | Every recommendation cites at least one governing clause by ID |
| FR-6 | Pause at a durable interrupt before any monetary action |
| FR-7 | On approval, execute the action workflow against the core-banking API |
| FR-8 | On rejection, perform no side effect but still record the outcome and reason |
| FR-9 | Persist the full trace: retrieved context, governing clause, approver, timestamp, outcome |
| FR-10 | Answer policy questions without opening a case (US-5) |

### 6.2 Mandated UI *(master prompt section 5 — all non-negotiable)*

| ID | Requirement |
|---|---|
| FR-11 | React + React Router + Vite + Tailwind. Minimal enterprise aesthetic. **No emojis.** Icons from Lucide only |
| FR-12 | Explicit light/dark toggle via CSS variables + Tailwind semantic tokens. No hardcoded colours anywhere |
| FR-13 | **Global header LLM monitor:** active call count, cumulative input/output tokens, estimated cost (LiteLLM fallback rates when the model is unpriced) |
| FR-14 | **Settings gear drawer:** gateway URL, port, and API key inputs; iOS-style "Disable SSL Verification" toggle; live cache hit/miss ratio |
| FR-15 | **Universal grounding panel:** vector embedding stats, graph entity/relationship counts, force-graph visualisation, dynamic document upload |
| FR-16 | Conflict banner: when `reconcile` finds a contradiction, the UI states it explicitly and shows the losing source alongside the governing one |
| FR-17 | Approval controls: approve / reject with a reason, disabled until a recommendation exists |
| FR-18 | KPI strip surfacing the section 9 metrics |

FR-16 is not in the master prompt. It is added because 1.4 makes reconciliation the product, and an
invisible differentiator is not a differentiator.

### 6.3 Platform

| ID | Requirement |
|---|---|
| FR-19 | Cross-platform `startup.sh` + `startup.bat` with pre-flight validation |
| FR-20 | Pre-flight verifies: venv, Node >=20, port 8787 free, data dir writable, gateway reachable, **every configured model ID present in `/v1/models`**, Neo4j reachable-or-fallback. Fails fast naming the exact missing item |
| FR-21 | Boot-time env validation via Pydantic settings schema |
| FR-22 | Exponential-backoff retries on 429/502/503 |
| FR-23 | Graceful shutdown on SIGINT/SIGTERM: flush logs, close DB and driver connections |
| FR-24 | Structured JSON logging per LLM call, graph query, and agent action: latency, tokens, model, cache hit/miss, with automatic secret/PII redaction |
| FR-25 | A2A conformance slice: `/.well-known/agent.json` agent card + JSON-RPC `message/send` |
| FR-26 | Mock core-banking API mounted as a router in-process (no second daemon): provisional credit, dispute case, customer notice |

---

## 7. Non-Functional Requirements

### 7.1 Runtime constraints *(non-negotiable)*

Zero Docker/containers. Zero root/admin. Zero system-wide background daemons. Python 3.11+ in
`venv`; Node 22.x recommended, >=20 accepted. Backend on **:8787**, frontend on **:5173** — both
unprivileged. All storage local and file-based, with the **single** exception of Neo4j AuraDB.

> **Conflict resolved:** master prompt section 2 specifies Node 22.x while section 3's pre-flight
> list says 20.x. Resolved as require >=20, recommend 22.

### 7.2 Security — TLS bypass trade-off *(stated explicitly)*

The environment uses intercepted corporate certificates. When `SSL_VERIFY=false`, an `httpx` client
with `verify=False` is injected into LangChain, Chroma, and the Neo4j driver from a single helper
(`app/tls.py`).

**The trade-off, stated plainly:** with verification disabled, the application **cannot distinguish
the corporate proxy from a hostile man-in-the-middle.** All gateway traffic — prompts, retrieved
context, and responses — is exposed to anyone able to intercept the connection.

This is acceptable **here and only here** because: the interception is known and corporate; all data
is synthetic; no production credentials or real customer PII are involved; and the deployment is a
local prototype. **It is not an acceptable production posture.** The correct production fix is to
trust the corporate root CA explicitly via `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`, not to disable
verification. A prominent warning banner is logged at boot whenever the flag is on, and the UI
reflects its state in the settings drawer.

### 7.3 Other NFRs

| Area | Requirement |
|---|---|
| Performance | Recommendation in <=90s p95 (dominated by pro-tier latency); UI interactions <200ms; telemetry poll every 1.5s |
| Neo4j handling | Reachability probed at pre-flight, not first use. Unreachable or credential-less means automatic Kuzu fallback, logged loudly and shown in the UI. **The demo must pass end to end on either backend** |
| Cost | Exact-match and semantic prompt caching in SQLite; cheapest viable tier per node |
| Maintainability | 300–400 LOC hard ceiling per file; single-responsibility modules; strict separation of concerns |
| Data | Synthetic only, deterministic seed, committed as fixtures for reproducibility |
| Auditability | Every decision reconstructable from SQLite alone, with no dependency on any SaaS trace |
| Resilience | No SaaS dependency (LangSmith, and Neo4j beyond pre-flight) may fail a user request |

---

## 8. Out of Scope (Anti-goals)

Explicitly excluded to protect the 2–3 day timebox. Listed so that absence reads as a decision, not
an oversight.

- **No production core-banking integration.** The action workflow calls a mock API by design.
- **No real PII.** Synthetic data only.
- **No unattended monetary action.** There is no "auto-approve" mode, at any confidence.
- **No auth, RBAC, or multi-tenancy.** A single demo operator identity.
- **No model fine-tuning or training.** Prompting, retrieval, and validation only.
- **No horizontal scaling, HA, or DR.**
- **No full A2A conformance.** FR-25 is a conformance slice — an agent card and one JSON-RPC method —
  not discovery, authentication, and cross-boundary negotiation. Described as such, not overclaimed.
- **No mobile or native client.**

### 8.1 Deliberate cuts from the problem statement *(flagged, not hidden)*

The challenge's *guidance* section mentions multimodal and multilingual data. Both are cut:

- **Multilingual — cut.** English only. Adds embedding-model and eval complexity disproportionate to
  the demo value at this timebox.
- **Multimodal — cut from the build, but architecturally provisioned.** Text only ships. The
  ingestion path is designed so that adding image/scanned-document support later is a registration,
  not a refactor. Four concrete provisions are binding on the implementation:
  1. `rag/ingest.py` dispatches to loaders through a **MIME-keyed registry**; a new modality is a new
     registered handler, not an edit to the ingestion flow.
  2. Every `Document` and `Chunk` carries a `modality` field (`text` today; `image` / `table`
     reserved) and a `source_uri`, so binary assets can be referenced without a schema migration.
  3. `GroundingContext` holds a list of **typed evidence items**, not a list of strings, so non-text
     evidence can join the context without changing the guard or the prompt assembly.
  4. The dispute schema carries an `attachments` field from day one. Non-text attachments are
     accepted, stored, and surfaced in the trace; they are simply not yet interpreted.

Cross-industry reusability is demonstrated **architecturally** — the domain pack (corpus, graph
schema, tools, precedence ladder) is config-and-data, not code — but only the banking pack ships.

---

## 9. Success Metrics

### 9.1 Product KPIs

| KPI | Baseline *(assumed, see 9.3)* | Target | Measurement |
|---|---|---|---|
| Task completion time | ~11 min/dispute | <=90s to recommendation | Wall clock, SQLite |
| Automation rate | 0% | >=60% resolved without escalation | Outcome column |
| Resolution quality | — | >=85% correct action | 20-case labelled eval set |
| Citation precision | — | 100% cite >=1 clause; >=90% cite the **correct** clause | Eval set |
| Conflict detection recall | — | **100% on C1–C3** | Eval set |
| User effort | ~6 system switches | <=2 interactions (review + approve) | UI event log |
| Compliance adherence | — | 100% state the applicable deadline | Eval set |

**Conflict detection recall is the headline metric.** Per 1.4 it is the differentiator; it is the
one target set at 100% and the one that must not be traded away.

### 9.2 Technical metrics

Cache hit ratio >=30% on the eval run · zero unhandled exceptions on the golden path · p95
recommendation latency <=90s · 100% of `GROUNDED` calls carry non-empty context (guard-enforced) ·
100% of eval cases pass on **both** graph backends.

### 9.3 Honesty note on baselines

The manual baselines in 9.1 (~11 min, ~6 system switches) are **stated assumptions used to frame
improvement, not measured observations.** No user study was run. They must be presented as
assumptions in any demo or report. The copilot-side numbers are genuinely measured; the baselines
are not.

---

## 10. Acceptance Criteria

The prototype is done when all ten pass:

1. `preflight.py` exits green, or fails fast naming the exact missing item
2. `startup.sh` / `startup.bat` bring up both services; `/health` returns OK
3. `seed_data.py` prints document, chunk, node, and relationship counts matching the grounding panel
4. Theme toggle repaints entirely via tokens, with no hardcoded colours
5. Header monitor increments tokens and cost during a query; drawer shows a non-zero cache hit ratio on a repeat
6. **Golden path:** dispute submitted, recommendation cites >=2 sources **and flags the engineered
   conflict**, approved, mock API returns 200, case row written with approver and timestamp
7. **Rejection path:** no mock-API side effect; outcome still recorded
8. `run_eval.py` emits KPI JSON meeting the 9.1 targets
9. **Fallback drill:** with Neo4j credentials unset, pre-flight selects Kuzu and the golden path still passes
10. **Guard test:** a `GROUNDED` call with empty context raises rather than answering from parametric memory

---

## 11. Roadmap Beyond the Prototype

**Near:** multimodal receipt/screenshot ingest · second domain pack to prove the config-only claim ·
full A2A · corporate root CA trust replacing the TLS bypass.
**Later:** RBAC and approval authority tiers · confidence-banded auto-approval below a monetary
threshold · continuous eval on production traffic · multilingual.
