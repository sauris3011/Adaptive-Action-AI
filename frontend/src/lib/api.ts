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
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
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
