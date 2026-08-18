/* iOS-style switch (FR-14). */
export function Toggle({
  checked,
  onChange,
  label,
  tone = 'default',
  id,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: string
  tone?: 'default' | 'danger'
  id: string
}) {
  const on = tone === 'danger' ? 'bg-danger' : 'bg-accent'
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full
                  transition-colors focus:outline-none focus:ring-2 focus:ring-accent
                  focus:ring-offset-2 focus:ring-offset-bg
                  ${checked ? on : 'bg-border-strong'}`}
    >
      <span
        className={`inline-block h-5 w-5 transform rounded-full bg-surface-raised shadow
                    transition-transform ${checked ? 'translate-x-[22px]' : 'translate-x-0.5'}`}
      />
    </button>
  )
}
