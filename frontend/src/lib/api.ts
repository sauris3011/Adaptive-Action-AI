import { z } from 'zod'

/* Every backend response is parsed through a Zod schema before it reaches a
   component (master prompt section 2: Pydantic in Python / Zod in TypeScript).
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
})
export type TelemetrySummary = z.infer<typeof TelemetrySummarySchema>

export const RuntimeSettingsSchema = z.object({
  gateway_url: z.string(),
  gateway_api_key_set: z.boolean(),
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

export const GraphStatsSchema = z.object({
  backend: z.string(),
  nodes: z.number(),
  relationships: z.number(),
  by_label: z.record(z.number()),
  by_relationship: z.record(z.number()),
  active_backend: z.string().optional(),
})

export const GroundingStatsSchema = z.object({
  vector: VectorStatsSchema,
  graph: GraphStatsSchema,
  relational: z.record(z.number()),
  supported_uploads: z.array(z.string()),
})
export type GroundingStats = z.infer<typeof GroundingStatsSchema>

export const GraphViewSchema = z.object({
  root: z.string().nullable(),
  found: z.boolean(),
  hops: z.number().nullable(),
  nodes: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      caption: z.string(),
      distance: z.number().optional(),
      props: z.record(z.unknown()),
    }),
  ),
  links: z.array(z.object({ source: z.string(), target: z.string(), label: z.string() })),
  truncated: z.boolean(),
})
export type GraphView = z.infer<typeof GraphViewSchema>
export type GraphNode = GraphView['nodes'][number]

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
  status: z.string(),
})
export type Run = z.infer<typeof RunSchema>

export const ACTION_LABELS: Record<string, string> = {
  provisional_credit: 'Issue provisional credit',
  goodwill_refund: 'Issue goodwill refund',
  route_to_fraud_ops: 'Route to Fraud Operations',
  request_merchant_contact: 'Request merchant contact',
  decline: 'Decline',
  answer_only: 'Answer only',
}

export class ApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(path, {
      ...init,
      /* FormData must set its own multipart boundary, so the JSON content type
         is omitted rather than overridden - an explicit header here would break
         the upload silently. */
      headers:
        init?.body instanceof FormData
          ? { ...(init?.headers ?? {}) }
          : { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch (cause) {
    throw new ApiError(`Cannot reach the backend at ${path}. Is it running on :8787?`)
  }

  if (!resp.ok) {
    const body = await resp.text().catch(() => '')
    let detail = body
    try {
      detail = JSON.parse(body).detail ?? body
    } catch {
      /* plain-text body */
    }
    throw new ApiError(detail || `HTTP ${resp.status}`, resp.status)
  }

  const parsed = schema.safeParse(await resp.json())
  if (!parsed.success) {
    throw new ApiError(`Unexpected response shape from ${path}: ${parsed.error.message}`)
  }
  return parsed.data
}

export const api = {
  health: () => request('/health', HealthSchema),
  telemetry: () => request('/api/telemetry/summary', TelemetrySummarySchema),
  settings: () => request('/api/settings', RuntimeSettingsSchema),
  modelCatalog: () => request('/api/settings/models', ModelCatalogSchema),
  updateSettings: (
    patch: Partial<{
      gateway_url: string
      gateway_api_key: string
      ssl_verify: boolean
      models: Record<string, string>
    }>,
  ) =>
    request('/api/settings', RuntimeSettingsSchema, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  smoke: (prompt: string) =>
    request('/api/copilot/smoke', SmokeResponseSchema, {
      method: 'POST',
      body: JSON.stringify({ prompt }),
    }),
  submitDispute: (body: {
    text: string
    transaction_id?: string | null
    customer_id?: string | null
  }) => request('/api/copilot/disputes', RunSchema, { method: 'POST', body: JSON.stringify(body) }),
  groundingStats: () => request('/api/grounding/stats', GroundingStatsSchema),
  graphView: (entity?: string, hops = 2) =>
    request(
      entity
        ? `/api/grounding/graph?entity=${encodeURIComponent(entity)}&hops=${hops}`
        : '/api/grounding/graph',
      GraphViewSchema,
    ),
  groundingSearch: (q: string, transactionId?: string) =>
    request(
      `/api/grounding/search?q=${encodeURIComponent(q)}` +
        (transactionId ? `&transaction_id=${encodeURIComponent(transactionId)}` : ''),
      SearchResultSchema,
    ),
  reseed: () => request('/api/grounding/reseed', ReseedResultSchema, { method: 'POST' }),
  uploadDocument: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    /* No Content-Type header: the browser must set the multipart boundary. */
    return request('/api/grounding/upload', UploadResultSchema, {
      method: 'POST',
      body,
      headers: {},
    })
  },
}

export function formatCost(usd: number): string {
  if (usd === 0) return '$0.00'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export function formatTokens(n: number): string {
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(2)}M`
}
