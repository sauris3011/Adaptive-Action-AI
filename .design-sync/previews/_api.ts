/* Some components fetch their own data on mount (KpiStrip, SettingsDrawer) or
   on submit (RetrievalPreview) rather than taking it as props. Importing this
   module installs a window.fetch shim that answers the backend routes with
   realistic fixtures, so the card shows the component's real populated render
   instead of "Loading…" or a connection error.

   This supplies data the component would have got from the backend. The
   component still renders itself — nothing here reimplements any markup. */
import { EVIDENCE } from './_fixtures'

const ROUTES: Record<string, unknown> = {
  '/api/kpi': {
    eval_available: true,
    eval_command: 'python backend/scripts/run_eval.py',
    eval: {
      generated_at: '2026-08-19T06:40:00Z', age_hours: 2.5, cases: 20, passed: 18,
      all_targets_met: false,
      product_kpis: [
        { name: 'Grounded citation rate', value: 96, target: 90, unit: '%', pass: true, detail: 'Citations resolving to retrieved evidence.' },
        { name: 'Correct action', value: 90, target: 85, unit: '%', pass: true, detail: 'Recommended action matches the labelled outcome.' },
        { name: 'Conflict resolved', value: 100, target: 100, unit: '%', pass: true, detail: 'All three engineered contradictions resolved by precedence.' },
        { name: 'Time to decision', value: 41, target: 60, unit: 's', pass: true, detail: 'Median wall clock from submission to recommendation.' },
      ],
      technical_kpis: [
        { name: 'Schema validity', value: 100, target: 100, unit: '%', pass: true, detail: 'Structured outputs passing Pydantic on first or repair attempt.' },
        { name: 'Ungrounded calls blocked', value: 100, target: 100, unit: '%', pass: true, detail: 'Guard rejections where grounding was absent.' },
        { name: 'Cache hit ratio', value: 40, target: 50, unit: '%', pass: false, detail: 'Prompt cache hits across the eval run.' },
        { name: 'p95 latency', value: 12.4, target: 15, unit: 's', pass: true, detail: '95th percentile end-to-end.' },
      ],
      assumed_baseline: {
        task_completion_seconds: 900, system_switches: 4, measured: false,
        note: 'Manual baseline is an assumption from the problem statement, not a measurement.',
      },
      latency_ms: { p50: 8200, p95: 12400 },
    },
    live: {
      cases_decided: 12, by_outcome: { approved: 8, rejected: 3, approved_action_failed: 1 },
      approval_rate_pct: 66.7, avg_latency_ms: 8420, max_latency_ms: 15310, avg_confidence: 0.81,
    },
  },
  '/api/settings': {
    gateway_url: 'http://localhost:4000', gateway_api_key_set: true,
    gateway_enabled: false,
    gateway_offline_reason: 'the LLM gateway is disabled (GATEWAY_ENABLED=false in .env, or the toggle in Settings)',
    ssl_verify: false,
    tls_warning: 'TLS VERIFICATION DISABLED. Outbound traffic cannot be distinguished from a man-in-the-middle. Prototype/synthetic data only - never a production posture.',
    models: { triage: 'gemini-2.5-flash-lite', digest: 'gemini-2.5-flash', reason: 'gemini-2.5-pro', embed: 'text-embedding-004' },
    unconfigured_roles: [], graph_backend: 'kuzu',
  },
  '/api/grounding/search': { query: 'unauthorised transaction with a fraud engine flag', count: EVIDENCE.length, evidence: EVIDENCE },
}

function match(url: string): unknown {
  const path = url.split('?')[0]
  return ROUTES[path] ?? ROUTES[Object.keys(ROUTES).find((k) => path.startsWith(k)) ?? '']
}

if (typeof window !== 'undefined' && !(window as { __dsStub?: boolean }).__dsStub) {
  ;(window as { __dsStub?: boolean }).__dsStub = true
  window.fetch = ((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const body = match(url)
    return Promise.resolve(
      body === undefined
        ? new Response('{"detail":"not stubbed"}', { status: 404, headers: { 'Content-Type': 'application/json' } })
        : new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
  }) as typeof fetch
}

export {}
