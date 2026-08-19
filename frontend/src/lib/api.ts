import { z } from 'zod'
import {
  AttachEvidenceSchema,
  BackendSwitchSchema,
  CaseListSchema,
  GraphAnswerSchema,
  GraphViewSchema,
  GroundingStatsSchema,
  KpiResponseSchema,
  HealthSchema,
  ModelCatalogSchema,
  ReseedResultSchema,
  RunSchema,
  RuntimeSettingsSchema,
  SearchResultSchema,
  SmokeResponseSchema,
  TelemetrySummarySchema,
  TransactionRowSchema,
  TransactionSearchSchema,
  UploadResultSchema,
  type GraphMethod,
  type Scope,
} from './schemas'

/* The HTTP client. Wire-format schemas live in schemas.ts and are re-exported
   here so every component keeps importing from one place. */

export * from './schemas'

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
      gateway_enabled: boolean
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
  getRun: (runId: string) => request(`/api/copilot/runs/${runId}`, RunSchema),
  approveRun: (runId: string, body: { approver: string; approver_role: string; note?: string }) =>
    request(`/api/copilot/runs/${runId}/approve`, RunSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  rejectRun: (runId: string, body: { approver: string; reason: string }) =>
    request(`/api/copilot/runs/${runId}/reject`, RunSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  cases: () => request('/api/copilot/cases', CaseListSchema),
  /* Graph evidence lands in the same run_events trace the pipeline writes to,
     so a reviewer does not have to know who added a piece of evidence to find
     it. */
  attachEvidence: (
    caseId: string,
    body: { resolved_call: string; method: string; entity: string | null; answer: string; backend: string },
  ) =>
    request(`/api/copilot/cases/${encodeURIComponent(caseId)}/evidence`, AttachEvidenceSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  kpis: () => request('/api/kpi', KpiResponseSchema),
  groundingStats: () => request('/api/grounding/stats', GroundingStatsSchema),
  graphView: (entity?: string, hops = 2) =>
    request(
      entity
        ? `/api/grounding/graph?entity=${encodeURIComponent(entity)}&hops=${hops}`
        : '/api/grounding/graph',
      GraphViewSchema,
    ),
  /* Filtering is server-side: the duplicate rule lives next to the table it
     reads, and the query shape stays the same when the record outgrows a
     fixture. */
  lookupTransactions: (q: string, scope: Scope) =>
    request(
      `/api/records/transactions?q=${encodeURIComponent(q)}&scope=${scope}`,
      TransactionSearchSchema,
    ),
  lookupTransaction: (transactionId: string) =>
    request(
      `/api/records/transactions/${encodeURIComponent(transactionId)}`,
      TransactionRowSchema,
    ),
  /* POST because the question is free text the operator typed, which is the
     wrong thing to put in a URL once it grows past a phrase. `method` is the
     chip tap - it overrides resolution rather than re-asking. */
  askGraph: (body: { question: string; method?: GraphMethod; hops?: number }) =>
    request('/api/grounding/ask', GraphAnswerSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  switchGraphBackend: (backend: 'neo4j' | 'kuzu') =>
    request('/api/grounding/backend', BackendSwitchSchema, {
      method: 'POST',
      body: JSON.stringify({ backend }),
    }),
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
