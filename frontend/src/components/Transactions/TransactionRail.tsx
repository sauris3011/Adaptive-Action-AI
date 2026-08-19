import { FileClock, TriangleAlert } from 'lucide-react'
import { Eyebrow } from '../ui/Eyebrow'
import { KeyValueRow } from '../ui/KeyValueRow'
import { StatCard } from '../ui/StatCard'
import { DISPUTE_OUTCOME_LABELS, type TransactionRow } from '../../lib/api'

/* Detail rail for the selected transaction.

   Everything here is the authoritative record. The fraud flag in particular
   exists in no policy document - it is the fact that makes conflict C3
   unresolvable from documents alone, so the rail states it rather than leaving
   it to be inferred from the row tint. */

/* Merchants sit between 0 and roughly 10% dispute rate in the pack, so the bar
   is scaled against a 10% ceiling. Scaling to the observed maximum instead
   would make the riskiest merchant look full whatever its actual rate. */
const RATE_CEILING = 0.1

function Alert({ row }: { row: TransactionRow }) {
  if (row.fraud_flag) {
    return (
      <div className="rounded-lg border border-danger bg-danger-subtle px-[13px] py-3">
        <div className="flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-danger">
          <TriangleAlert size={12} aria-hidden="true" />
          Fraud flag set
        </div>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-text">
          The fraud engine flagged this at authorisation. Under FSP-1.2 this routes to Fraud Ops
          and does not open a dispute case — no document contains this fact.
        </p>
      </div>
    )
  }

  if (row.duplicate_of) {
    return (
      <div className="rounded-lg border border-warning bg-warning-subtle px-[13px] py-3">
        <div className="flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-warning">
          <TriangleAlert size={12} aria-hidden="true" />
          Possible duplicate
        </div>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-text">
          Same merchant and amount as {row.duplicate_of} within seven days. Check for a duplicate
          before treating either as unauthorised.
        </p>
      </div>
    )
  }

  return null
}

/* Rendered outside <Alert> on purpose. The server ranks fraud above disputed in
   `signal`, so a fraud-flagged transaction with an open case would otherwise
   show only the flag - and "there is already a case on this" is exactly what
   stops the operator opening a second one. */
function DisputeStrip({ row }: { row: TransactionRow }) {
  if (!row.dispute_id) return null
  const outcome = row.dispute_outcome ?? ''
  const label = DISPUTE_OUTCOME_LABELS[outcome] ?? outcome

  return (
    <div
      className={`rounded-lg px-[13px] py-3 ${
        row.disputed
          ? 'border border-info bg-info-subtle'
          : 'border border-dashed border-border-strong bg-surface-raised'
      }`}
    >
      <div
        className={`flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] ${
          row.disputed ? 'text-info' : 'text-text-subtle'
        }`}
      >
        <FileClock size={12} aria-hidden="true" />
        {row.disputed ? 'Dispute open' : 'Prior dispute'}
      </div>
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-text">
        <span className="font-mono text-[11.5px]">{row.dispute_id}</span> — {label}.{' '}
        {row.disputed
          ? 'It is on the record and in the graph, so the next run retrieves it as prior history.'
          : 'Closed, so a fresh intake is still allowed.'}
      </p>
    </div>
  )
}

function MerchantContext({ row, onAskGraph }: { row: TransactionRow; onAskGraph: () => void }) {
  const rate = row.dispute_rate ?? 0
  const band = (row.risk_band ?? 'unknown').toLowerCase()
  const hot = band === 'high' || band === 'elevated'
  const width = `${Math.min(100, Math.round((rate / RATE_CEILING) * 100))}%`

  return (
    <div>
      <Eyebrow>Merchant context</Eyebrow>
      <div className="card mt-2 flex flex-col gap-2 px-[13px] py-3">
        <KeyValueRow label="risk band" value={band} tone={hot ? 'danger' : 'default'} />
        <KeyValueRow label="category" value={row.merchant_category ?? 'unknown'} />
        <div>
          <KeyValueRow
            label="dispute rate"
            value={`${(rate * 100).toFixed(1)}%`}
            tone={hot ? 'danger' : 'neutral'}
          />
          <div className="mt-1.5 h-1 overflow-hidden rounded-sm bg-border">
            <div className={`h-full ${hot ? 'bg-danger' : 'bg-text-muted'}`} style={{ width }} />
          </div>
        </div>
        <button
          type="button"
          onClick={onAskGraph}
          className="text-left text-xs font-medium text-accent hover:text-accent-hover"
        >
          Ask the graph about {row.merchant_name} →
        </button>
      </div>
    </div>
  )
}

export function TransactionRail({
  row,
  onAskGraph,
}: {
  row: TransactionRow | null
  onAskGraph: (merchantName: string) => void
}) {
  if (!row) {
    return (
      <div className="flex flex-col gap-[9px] pt-2">
        <Eyebrow>No transaction selected</Eyebrow>
        <p className="text-[13px] leading-relaxed text-text-muted">
          Pick a row to see the authoritative record, the fraud flag, and merchant history — then
          open it as a case.
        </p>
        <div className="rounded-lg border border-dashed border-border-strong bg-surface-raised p-4 font-mono text-[11.5px] leading-relaxed text-text-subtle">
          facts · flags · merchant risk
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Eyebrow>Selected transaction</Eyebrow>
        <div className="mt-1.5 text-base font-semibold text-text">{row.transaction_id}</div>
        <div className="mt-1 text-xs text-text-muted">
          {row.merchant_name} · {row.date_label}
        </div>
      </div>

      <StatCard>
        <KeyValueRow label="amount" value={`${row.amount.toFixed(2)} ${row.currency}`} />
        <KeyValueRow label="merchant" value={row.merchant_name} />
        <KeyValueRow label="category" value={row.merchant_category ?? 'unknown'} />
        <KeyValueRow label="channel" value={row.channel ?? 'unknown'} />
        <KeyValueRow
          label="status"
          value={row.status ?? 'unknown'}
          tone={row.signal === 'reversed' ? 'warning' : 'default'}
        />
        <KeyValueRow
          label="fraud_flag"
          value={String(row.fraud_flag)}
          tone={row.fraud_flag ? 'danger' : 'default'}
        />
      </StatCard>

      <Alert row={row} />

      <DisputeStrip row={row} />

      <MerchantContext row={row} onAskGraph={() => onAskGraph(row.merchant_name)} />

      <p className="border-t border-border pt-[13px] text-[11.5px] leading-relaxed text-text-muted">
        Opening a dispute writes it to the record and projects it into the graph, so the next run
        retrieves it as prior history. Nothing here came from a document.
      </p>
    </div>
  )
}
