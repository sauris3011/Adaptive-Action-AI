/* Shared preview fixtures — realistic dispute-domain data drawn from the
   repo's own banking domain pack (backend/domain/banking). Kept in one place
   so every card tells a consistent story: the same dispute, the same clauses,
   the same customer. Not a component; the converter only compiles <Name>.tsx. */
import type { Conflict, Evidence, Recommendation, Run } from 'adaptive-action-copilot-ui'

export const EVIDENCE: Evidence[] = [
  {
    kind: 'policy', ref: 'REG-E-2', title: 'Provisional credit timing',
    content:
      'Where the institution cannot complete its investigation within 10 business days of notice, it must provisionally credit the disputed amount to the consumer account pending the outcome.',
    modality: 'text', tier: 1, source_uri: 'corpus/reg-e.md', score: 0.881,
  },
  {
    kind: 'policy', ref: 'BDP-3.4', title: 'Agent authorisation limit',
    content:
      'Agents may approve provisional credit up to 500.00 USD. Above that threshold a Team Lead approval is mandatory and must be recorded against the case.',
    modality: 'text', tier: 3, source_uri: 'corpus/bank-dispute-policy.md', score: 0.774,
  },
  {
    kind: 'policy', ref: 'GRS-2.3', title: 'Goodwill refund discretion',
    content:
      'A goodwill refund may be offered at the agent\u2019s discretion for amounts under 50.00 USD where the merchant relationship is otherwise sound.',
    modality: 'text', tier: 3, source_uri: 'corpus/goodwill-refund-sop.md', score: 0.612,
  },
  {
    kind: 'graph', ref: 'TXN-9002', title: 'Transaction \u2192 Merchant \u2192 Dispute',
    content:
      'TXN-9002 (240.00 USD, card-present) AT Northwind Electronics. RAISED as DSP-1183 by A. Sharma on 2026-08-14.',
    modality: 'graph', tier: null, source_uri: null, score: null,
  },
  {
    kind: 'record', ref: 'TXN-9002', title: 'Transaction record',
    content:
      'amount: 240.00 USD\nfraud_flag: true\nchannel: card_present\nposted_at: 2026-08-13T19:41:00Z',
    modality: 'record', tier: null, source_uri: null, score: null,
  },
]

export const RECOMMENDATION: Recommendation = {
  action: 'route_to_fraud_ops',
  headline: 'Route to Fraud Operations before any credit is issued',
  rationale:
    'The transaction record carries a fraud flag that appears in no policy document \u2014 only in the ledger. '
    + 'REG-E-2 would ordinarily require provisional credit within 10 business days, but a flagged transaction is '
    + 'routed to Fraud Operations first: crediting a suspected-fraud account ahead of triage would fund the loss. '
    + 'The 10-day clock continues to run and is preserved on the case.',
  citations: ['REG-E-2', 'BDP-3.4', 'TXN-9002'],
  governing_clause: 'REG-E-2',
  deadline: '2026-08-28 (10 business days from notice)',
  amount: 240.0,
  requires_approval: true,
  confidence: 0.86,
  caveats:
    'The fraud flag is a record-level fact, not a policy conclusion. If Fraud Operations clears the transaction, '
    + 'the provisional-credit obligation under REG-E-2 resumes on the original clock.',
}

export const CONFLICTS: Conflict[] = [
  {
    description:
      'REG-E-2 requires provisional credit within 10 business days; BDP-3.4 caps agent-approved credit at 500.00 USD.',
    governing_clause: 'REG-E-2',
    governing_tier: 1,
    superseded_clauses: ['GRS-2.3'],
    is_true_conflict: true,
    resolution_basis:
      'Regulatory requirement outranks bank policy and SOP. BDP-3.4 does not waive the obligation \u2014 it decides who signs it off, so the credit still issues, at Team Lead level.',
  },
  {
    description:
      'GRS-2.3 offers a goodwill refund under 50.00 USD; REG-E-2 governs the disputed 240.00 USD amount.',
    governing_clause: 'REG-E-2',
    governing_tier: 1,
    superseded_clauses: ['GRS-2.3'],
    is_true_conflict: false,
    resolution_basis:
      'Different instruments, not a contradiction. A goodwill refund is discretionary and capped below this amount; it was never in scope for a 240.00 USD regulated dispute.',
  },
]

export const RUN_AWAITING: Run = {
  run_id: 'run-8f2c41ad', started_at: '2026-08-19T09:12:04Z', elapsed_ms: 8420,
  request_text: 'I did not authorise a 240 USD payment to Northwind Electronics on 13 August.',
  transaction_id: 'TXN-9002', customer_id: 'CUST-1042', triage: null,
  evidence: EVIDENCE,
  reconciliation: { conflicts: CONFLICTS, notes: 'Precedence ladder applied: tier 1 over tier 3.' },
  recommendation: RECOMMENDATION,
  decision: null, approver: null, approved_at: null, reject_reason: null, case_id: null,
  action_results: [],
  planned_actions: [
    { instrument: 'dispute_case', payload: {} },
    { instrument: 'provisional_credit', payload: {} },
    { instrument: 'customer_notice', payload: {} },
  ],
  status: 'awaiting_approval',
}

export const RUN_APPROVED: Run = {
  ...RUN_AWAITING,
  decision: 'approved', approver: 'Priya Nair', approved_at: '2026-08-19T09:14:31Z',
  case_id: 'CASE-2026-0431', status: 'approved',
  action_results: [
    { instrument: 'dispute_case', reference: 'DSP-1183', status_code: 200 },
    { instrument: 'provisional_credit', reference: 'PC-77120', status_code: 200, idempotent: true },
    { instrument: 'customer_notice', reference: 'NTC-4410', status_code: 200 },
  ],
  effects: {
    provisional_credits: [{ reference: 'PC-77120' }],
    dispute_cases: [{ reference: 'DSP-1183' }],
    notices: [{ reference: 'NTC-4410' }],
  },
}

export const RUN_REJECTED: Run = {
  ...RUN_AWAITING,
  decision: 'rejected', approver: 'Priya Nair', approved_at: '2026-08-19T09:15:02Z',
  reject_reason: 'Customer confirmed the charge on a call back; no dispute to raise.',
  case_id: 'CASE-2026-0432', status: 'rejected',
  action_results: [],
  effects: { provisional_credits: [], dispute_cases: [], notices: [] },
}

export const TELEMETRY = {
  active_calls: 0, total_calls: 47,
  input_tokens: 128_400, output_tokens: 31_950, total_tokens: 160_350,
  estimated_cost_usd: 0.4382,
  cache_hits: 19, cache_misses: 28, cache_hit_ratio: 0.404,
  errors: 0,
}

export const TELEMETRY_BUSY = {
  ...TELEMETRY, active_calls: 3, total_calls: 50, errors: 2,
}
