import type { Tone } from '../../lib/api'

/* Tone-coded fact tag, as used under a graph answer.

   The class pairs are spelled out rather than composed from the tone name:
   Tailwind's scanner only sees literal class strings, so `bg-${tone}-subtle`
   would compile to nothing at all. */
const TONE_CLASS: Record<Tone, string> = {
  danger: 'bg-danger-subtle text-danger',
  warning: 'bg-warning-subtle text-warning',
  success: 'bg-success-subtle text-success',
  info: 'bg-info-subtle text-info',
  neutral: 'bg-border text-text-muted',
}

export function ToneTag({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return (
    <span
      className={`rounded px-2 py-[3px] font-mono text-[11px] font-medium ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  )
}
