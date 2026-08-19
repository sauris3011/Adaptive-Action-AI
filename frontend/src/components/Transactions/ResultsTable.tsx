import { EmptyState } from '../ui/EmptyState'
import { SignalBadge } from '../ui/SignalBadge'
import type { TransactionRow } from '../../lib/api'

/* The result list for the look-up (FR-2).

   Signals live in the list rather than on a detail page because they change the
   recommended route before any model runs: an operator scanning for the right
   transaction needs to see that one of them is fraud-flagged without opening it.

   Rows are real <button>s. They are the primary interaction on the screen, and
   a div with a click handler is not reachable by keyboard. */

const COLUMNS = 'flex items-center gap-3 px-4'

function HeaderRow() {
  return (
    <div
      className={`${COLUMNS} border-b border-border bg-surface py-[9px] font-mono text-[10px] font-medium uppercase tracking-[0.06em] text-text-subtle`}
    >
      <span className="w-[60px] flex-none">Date</span>
      <span className="w-24 flex-none">Ref</span>
      <span className="flex-1">Merchant</span>
      <span className="w-[84px] flex-none text-right">Amount</span>
      <span className="w-[78px] flex-none">Signal</span>
    </div>
  )
}

function rowTone(row: TransactionRow, selected: boolean): string {
  /* Precedence, not a merge: a selected fraud row reads as selected. Disputed
     sits below fraud for the same reason the server ranks the signals that way
     - an open case must not tint over the flag that decides the route. */
  if (selected) return 'bg-accent-subtle border-l-accent'
  if (row.fraud_flag) return 'bg-danger-subtle border-l-danger hover:bg-danger-subtle/70'
  if (row.disputed) return 'bg-info-subtle border-l-info hover:bg-info-subtle/70'
  return 'bg-surface-raised border-l-transparent hover:bg-surface'
}

export function ResultsTable({
  rows,
  selectedId,
  onSelect,
  query,
  scopeNote,
  onClearQuery,
  loading,
}: {
  rows: TransactionRow[]
  selectedId: string | null
  onSelect: (row: TransactionRow) => void
  query: string
  scopeNote: string
  onClearQuery: () => void
  loading: boolean
}) {
  return (
    <div className="mt-[9px] overflow-hidden rounded-[9px] border border-border bg-surface-raised">
      <HeaderRow />

      {loading && !rows.length ? (
        <div className="px-4 py-[34px] text-center text-[13px] text-text-subtle">
          Reading the record…
        </div>
      ) : rows.length ? (
        rows.map((row) => {
          const selected = row.transaction_id === selectedId
          return (
            <button
              key={row.transaction_id}
              type="button"
              aria-pressed={selected}
              onClick={() => onSelect(row)}
              className={`${COLUMNS} w-full border-b border-l-[3px] border-b-border py-3 text-left transition-colors ${rowTone(
                row,
                selected,
              )}`}
            >
              <span className="w-[60px] flex-none font-mono text-[11.5px] text-text-muted">
                {row.date_label}
              </span>
              <span className="w-24 flex-none font-mono text-[11.5px] text-text-muted">
                {row.transaction_id}
              </span>
              <span className="flex-1 truncate text-[13px] text-text">{row.merchant_name}</span>
              <span className="tnum w-[84px] flex-none text-right font-mono text-[12.5px] font-semibold text-text">
                {row.amount.toFixed(2)}
              </span>
              <span className="w-[78px] flex-none">
                <SignalBadge signal={row.signal} />
              </span>
            </button>
          )
        })
      ) : (
        <EmptyState
          title={
            query ? (
              <>
                Nothing matches “{query}” in {scopeNote}.
              </>
            ) : (
              <>No transactions in {scopeNote}.</>
            )
          }
          hint="Try a wider window, or paste the reference from the cardholder's statement."
          action={query ? { label: 'Clear search', onClick: onClearQuery } : undefined}
        />
      )}
    </div>
  )
}
