import type { Tone } from '../../lib/api'

const VALUE_CLASS: Record<Tone | 'default', string> = {
  default: 'text-text',
  danger: 'text-danger',
  warning: 'text-warning',
  success: 'text-success',
  info: 'text-info',
  neutral: 'text-text-muted',
}

/* One fact from the record: monospace key on the left, value hard right.

   Values carry `.tnum` because these rows sit in a fixed-width rail and a
   proportional digit set makes the column edge shuffle as the selection
   changes. */
export function KeyValueRow({
  label,
  value,
  tone = 'default',
}: {
  label: string
  value: React.ReactNode
  tone?: Tone | 'default'
}) {
  return (
    <div className="flex justify-between gap-2.5 font-mono text-[11.5px]">
      <span className="text-text-muted">{label}</span>
      <span className={`tnum font-semibold ${VALUE_CLASS[tone]}`}>{value}</span>
    </div>
  )
}
