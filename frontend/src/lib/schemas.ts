import { z } from 'zod'

import { GraphStatsSchema } from './schemas.records'

/* The record screens' contracts - and the graph-store shapes they share with
   the grounding panel - live next door, re-exported here so the single import
   surface ('../lib/api') is unchanged and both files stay inside the 300-400
   LOC ceiling (PRD 7.3). The dependency runs one way: this file imports from
   schemas.records, never the reverse. */
export * from './schemas.records'

/* Wire-format contracts, split out of api.ts to keep both files inside the
   300-400 LOC ceiling (PRD 7.3). api.ts re-exports everything here, so nothing
   that imports from '../lib/api' had to change.

   Every backend response is parsed through one of these before it reaches a
   component (master prompt section 2: Pydantic in Python, Zod in TypeScript).
   The backend already validates its own LLM output with Pydantic; this is the
   second gate, so a shape drift shows up as a named parse error rather than an
   undefined halfway down a render tree. */
export const TelemetrySummarySchema = z.object({
  active_calls: z.number(),
  total_calls: z.number(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  total_tokens: z.number(),
  estimated_cost_usd: z.number(),
  cache_hits: z.number(),
  cache_misses: z.number(),
  cache_hit_ratio: z.number(),
  errors: z.number(),
  /* Health rides this poll rather than a second timer (FR-13): the header
     already asks this endpoint every 1.5s, and two pollers for one strip of the
     header is a moving part with no user-visible benefit. */
  graph_backend: z.string(),
  graph_fallback: z.boolean(),
  gateway_enabled: z.boolean(),
})
export type TelemetrySummary = z.infer<typeof TelemetrySummarySchema>

export const RuntimeSettingsSchema = z.object({
  gateway_url: z.string(),
  gateway_api_key_set: z.boolean(),
  gateway_enabled: z.boolean(),
  /* Set only while the gateway is off, so the drawer can explain the inert
     model dropdowns instead of looking broken. */
  gateway_offline_reason: z.string().nullable(),
  ssl_verify: z.boolean(),
  tls_warning: z.string().nullable(),
  models: z.record(z.string()),
  unconfigured_roles: z.array(z.string()),
  graph_backend: z.string(),
})
export type RuntimeSettings = z.infer<typeof RuntimeSettingsSchema>

/* Discovered from the gateway on demand - never a hardcoded list in the UI. */
export const ModelCatalogSchema = z.object({
  gateway_url: z.string(),
  models: z.array(z.string()),
  embedding_models: z.array(z.string()),
  probed_at: z.string(),
})
export type ModelCatalog = z.infer<typeof ModelCatalogSchema>

export const HealthSchema = z.object({
  status: z.string(),
  version: z.string(),
  graph_backend: z.string(),
  tls_warning: z.string().nullable(),
})
export type Health = z.infer<typeof HealthSchema>

export const SmokeResponseSchema = z.object({
  reply: z.string(),
  model_role: z.string(),
})


/* --- Grounding (FR-15) ------------------------------------------------- */

export const EmbedderSchema = z.object({
  backend: z.string(),
  degraded: z.boolean(),
  dimension: z.number(),
})

export const VectorStatsSchema = z.object({
  collection: z.string(),
  chunks: z.number(),
  documents: z.number(),
  by_tier: z.record(z.number()),
  by_document: z.record(z.number()),
  embedder: EmbedderSchema,
  path: z.string(),
})

export const GroundingStatsSchema = z.object({
  vector: VectorStatsSchema,
  graph: GraphStatsSchema,
  relational: z.record(z.number()),
  supported_uploads: z.array(z.string()),
})
export type GroundingStats = z.infer<typeof GroundingStatsSchema>

export const EvidenceSchema = z.object({
  kind: z.enum(['policy', 'graph', 'record']),
  ref: z.string(),
  title: z.string(),
  content: z.string(),
  modality: z.string(),
  tier: z.number().nullable(),
  source_uri: z.string().nullable(),
  score: z.number().nullable(),
})
export type Evidence = z.infer<typeof EvidenceSchema>

export const SearchResultSchema = z.object({
  query: z.string(),
  count: z.number(),
  evidence: z.array(EvidenceSchema),
})

export const UploadResultSchema = z.object({
  filename: z.string().nullable(),
  documents: z.array(z.string()),
  chunks: z.number(),
  skipped: z.array(z.object({ path: z.string(), reason: z.string(), mime: z.string() })),
  stats: VectorStatsSchema,
})

export const ReseedResultSchema = z.object({
  documents: z.number(),
  chunks: z.number(),
  policy_edges: z.number(),
  skipped: z.array(z.object({ path: z.string(), reason: z.string(), mime: z.string() })),
  vector: VectorStatsSchema,
  graph: GraphStatsSchema,
  relational: z.record(z.number()),
})

export const TIER_LABELS: Record<number, string> = {
  1: 'Regulatory requirement',
  2: 'Card network rules',
  3: 'Bank policy & SOP',
  4: 'Product terms & conditions',
}


/* --- Copilot workflow (Stage 3) ---------------------------------------- */

export const TriageSchema = z.object({
  intent: z.enum(['dispute_intake', 'policy_question']),
  transaction_id: z.string().nullable(),
  customer_id: z.string().nullable(),
  merchant_hint: z.string().nullable(),
  amount: z.number().nullable(),
  reason_code: z.string(),
  summary: z.string(),
  retrieval_query: z.string(),
})

export const ConflictSchema = z.object({
  description: z.string(),
  governing_clause: z.string(),
  governing_tier: z.number(),
  superseded_clauses: z.array(z.string()),
  is_true_conflict: z.boolean(),
  resolution_basis: z.string(),
})
export type Conflict = z.infer<typeof ConflictSchema>

export const ReconciliationSchema = z.object({
  conflicts: z.array(ConflictSchema),
  notes: z.string(),
})

export const RecommendationSchema = z.object({
  action: z.string(),
  headline: z.string(),
  rationale: z.string(),
  citations: z.array(z.string()),
  governing_clause: z.string(),
  deadline: z.string(),
  amount: z.number().nullable(),
  requires_approval: z.boolean(),
  confidence: z.number(),
  caveats: z.string(),
})
export type Recommendation = z.infer<typeof RecommendationSchema>

export const ActionResultSchema = z.object({
  instrument: z.string(),
  reference: z.string(),
  status_code: z.number(),
  idempotent: z.boolean().optional(),
  detail: z.record(z.unknown()).optional(),
})
export type ActionResult = z.infer<typeof ActionResultSchema>

export const PlannedActionSchema = z.object({
  instrument: z.string(),
  payload: z.record(z.unknown()),
})
export type PlannedAction = z.infer<typeof PlannedActionSchema>

export const CaseSchema = z.object({
  case_id: z.string(),
  run_id: z.string(),
  created_at: z.string(),
  customer_id: z.string().nullable(),
  transaction_id: z.string().nullable(),
  reason_code: z.string().nullable(),
  recommendation: z.string().nullable(),
  governing_clause: z.string().nullable(),
  confidence: z.number().nullable(),
  outcome: z.string(),
  approver: z.string().nullable(),
  approved_at: z.string().nullable(),
  reject_reason: z.string().nullable(),
  elapsed_ms: z.number().nullable(),
})
export type DisputeCase = z.infer<typeof CaseSchema>

export const EffectsSchema = z.object({
  provisional_credits: z.array(z.record(z.unknown())),
  dispute_cases: z.array(z.record(z.unknown())),
  notices: z.array(z.record(z.unknown())),
})

export const RunSchema = z.object({
  run_id: z.string().nullable(),
  started_at: z.string().nullable(),
  elapsed_ms: z.number(),
  request_text: z.string().nullable(),
  transaction_id: z.string().nullable(),
  customer_id: z.string().nullable(),
  triage: TriageSchema.nullable(),
  evidence: z.array(EvidenceSchema),
  reconciliation: ReconciliationSchema.nullable(),
  recommendation: RecommendationSchema.nullable(),
  decision: z.string().nullable(),
  approver: z.string().nullable(),
  approved_at: z.string().nullable(),
  reject_reason: z.string().nullable(),
  case_id: z.string().nullable(),
  action_results: z.array(ActionResultSchema),
  planned_actions: z.array(PlannedActionSchema),
  status: z.string(),
  /* Present only on approve/reject/get responses, not on the initial submit. */
  effects: EffectsSchema.optional(),
  case: CaseSchema.nullable().optional(),
})
export type Run = z.infer<typeof RunSchema>


export const CaseListSchema = z.object({
  cases: z.array(CaseSchema),
  by_outcome: z.record(z.number()),
})

export const INSTRUMENT_LABELS: Record<string, string> = {
  dispute_case: 'Dispute case',
  provisional_credit: 'Provisional credit',
  customer_notice: 'Customer notice',
}

export const ACTION_LABELS: Record<string, string> = {
  provisional_credit: 'Issue provisional credit',
  goodwill_refund: 'Issue goodwill refund',
  route_to_fraud_ops: 'Route to Fraud Operations',
  request_merchant_contact: 'Request merchant contact',
  decline: 'Decline',
  answer_only: 'Answer only',
}



/* --- KPIs (FR-18) ------------------------------------------------------- */

export const KpiSchema = z.object({
  name: z.string(),
  value: z.number(),
  target: z.number(),
  unit: z.string(),
  pass: z.boolean(),
  detail: z.string(),
})
export type Kpi = z.infer<typeof KpiSchema>

export const EvalReportSchema = z.object({
  generated_at: z.string(),
  age_hours: z.number(),
  cases: z.number(),
  passed: z.number(),
  all_targets_met: z.boolean(),
  product_kpis: z.array(KpiSchema),
  technical_kpis: z.array(KpiSchema),
  assumed_baseline: z.object({
    task_completion_seconds: z.number(),
    system_switches: z.number(),
    measured: z.boolean(),
    note: z.string(),
  }),
  latency_ms: z.record(z.number()),
})

export const KpiResponseSchema = z.object({
  eval: EvalReportSchema.nullable(),
  live: z.object({
    cases_decided: z.number(),
    by_outcome: z.record(z.number()),
    approval_rate_pct: z.number(),
    avg_latency_ms: z.number(),
    max_latency_ms: z.number(),
    avg_confidence: z.number(),
  }),
  eval_available: z.boolean(),
  eval_command: z.string(),
})
export type KpiResponse = z.infer<typeof KpiResponseSchema>
