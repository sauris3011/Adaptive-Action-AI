import { z } from 'zod'

/* Wire formats for the two record screens, plus the graph-store shapes the
   grounding panel shares with them.

   Split out of schemas.ts on size alone (PRD 7.3) and re-exported from there,
   so nothing importing from '../lib/api' has to know this file exists. It
   imports nothing from schemas.ts: a cycle between the two would leave one of
   them reading a schema still in its temporal dead zone. */

export const GraphStatsSchema = z.object({
  backend: z.string(),
  nodes: z.number(),
  relationships: z.number(),
  by_label: z.record(z.number()),
  by_relationship: z.record(z.number()),
  active_backend: z.string().optional(),
})

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

/* --- Transaction look-up (FR-2, structured half) ------------------------ */

/* `signal` and `duplicate_of` are computed on the server from the record. They
   arrive as facts precisely so the UI cannot be accused of deriving a routing
   input in the browser - see backend/app/db/lookup.py. */
export const TransactionSignalSchema = z.enum(['fraud', 'disputed', 'duplicate', 'reversed'])
export type TransactionSignal = z.infer<typeof TransactionSignalSchema>

export const TransactionRowSchema = z.object({
  transaction_id: z.string(),
  account_id: z.string(),
  customer_id: z.string(),
  merchant_id: z.string(),
  amount: z.number(),
  currency: z.string(),
  posted_at: z.string().nullable(),
  channel: z.string().nullable(),
  fraud_flag: z.boolean(),
  fraud_score: z.number(),
  auth_code: z.string().nullable(),
  status: z.string().nullable(),
  customer_name: z.string().nullable(),
  product_tier: z.string().nullable(),
  merchant_name: z.string(),
  merchant_category: z.string().nullable(),
  merchant_country: z.string().nullable(),
  dispute_rate: z.number().nullable(),
  risk_band: z.string().nullable(),
  date_label: z.string(),
  card_last4: z.string(),
  duplicate_of: z.string().nullable(),
  /* An OPEN dispute is what `disputed` means. A resolved one still arrives as
     dispute_id/dispute_outcome so the rail can show the history without the
     screen refusing a fresh intake over a case closed last year. */
  dispute_id: z.string().nullable(),
  dispute_outcome: z.string().nullable(),
  /* Null for the seeded fixture disputes, which never had a run. */
  dispute_run_id: z.string().nullable(),
  disputed: z.boolean(),
  signal: TransactionSignalSchema.nullable(),
})
export type TransactionRow = z.infer<typeof TransactionRowSchema>

export const TransactionSearchSchema = z.object({
  query: z.string(),
  scope: z.string(),
  /* The day the scope window counts back from - the domain pack is a fixture
     with fixed dates, so "last 30 days" needs a stated anchor. */
  as_of: z.string(),
  count: z.number(),
  total: z.number(),
  transactions: z.array(TransactionRowSchema),
})
export type TransactionSearch = z.infer<typeof TransactionSearchSchema>

export const SCOPES = [
  { id: '30d', label: '30 days', note: 'last 30 days' },
  { id: '90d', label: '90 days', note: 'last 90 days' },
  { id: 'all', label: 'All', note: 'all history' },
] as const
export type Scope = (typeof SCOPES)[number]['id']

export const SIGNAL_LABELS: Record<TransactionSignal, string> = {
  fraud: 'FRAUD',
  disputed: 'DISPUTED',
  duplicate: 'DUPLICATE',
  reversed: 'REVERSED',
}

/* Human labels for the dispute vocabulary in backend/app/db/records.py. */
export const DISPUTE_OUTCOME_LABELS: Record<string, string> = {
  open: 'open, awaiting decision',
  resolved_credit: 'resolved with credit',
  goodwill_refund: 'goodwill refund',
  routed_to_fraud_ops: 'routed to Fraud Ops',
  awaiting_merchant_contact: 'awaiting merchant contact',
  rejected: 'rejected',
  action_failed: 'approved, action failed',
  resolved: 'resolved',
}


/* --- Graph search over the fixed five-query surface (FR-15) ------------- */

export const ToneSchema = z.enum(['danger', 'warning', 'success', 'info', 'neutral'])
export type Tone = z.infer<typeof ToneSchema>

export const GRAPH_METHODS = [
  'merchant_risk_profile',
  'customer_dispute_history',
  'transaction_context',
  'policy_dependencies',
  'neighborhood',
] as const
export type GraphMethod = (typeof GRAPH_METHODS)[number]

export const GraphAnswerSchema = z.object({
  question: z.string(),
  resolved: z.object({
    method: z.string(),
    entity: z.string().nullable(),
    /* Always rendered. A wrong answer is only recoverable if the operator can
       see which of the five produced it. */
    display: z.string(),
  }),
  answer: z.string(),
  tags: z.array(z.object({ label: z.string(), tone: ToneSchema })),
  view: GraphViewSchema,
  backend: z.string(),
  hops: z.number(),
  /* The rail's query list, served by the backend so it cannot drift from the
     GraphStore protocol it describes. */
  surface: z.array(z.object({ id: z.string(), description: z.string() })),
  latency_ms: z.number().optional(),
})
export type GraphAnswer = z.infer<typeof GraphAnswerSchema>

export const BackendSwitchSchema = z.object({
  active_backend: z.string(),
  graph: GraphStatsSchema,
})

export const AttachEvidenceSchema = z.object({
  case_id: z.string(),
  run_id: z.string(),
  attached: z.boolean(),
})
