import { SIGNAL_LABELS, type TransactionSignal } from '../../lib/api'

/* Record-level signal in a results row.

   Always renders the word as well as the colour (FR-11): FRAUD and DUPLICATE
   change the recommended route before any model runs, so they cannot be
   information carried by hue alone. DISPUTED is stronger still - it means an
   action is already in flight against this transaction. */
const SIGNAL_CLASS: Record<TransactionSignal, string> = {
  fraud: 'text-danger',
  disputed: 'text-info',
  duplicate: 'text-warning',
  reversed: 'text-text-subtle',
}

export function SignalBadge({ signal }: { signal: TransactionSignal | null }) {
  if (!signal) return null
  return (
    <span
      className={`font-mono text-[10px] font-semibold tracking-[0.05em] ${SIGNAL_CLASS[signal]}`}
    >
      {SIGNAL_LABELS[signal]}
    </span>
  )
}
