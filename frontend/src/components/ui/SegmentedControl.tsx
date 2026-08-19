/* Segmented control, used for the look-up's scope window.

   `flex-none whitespace-nowrap` on the options is load-bearing, not decoration:
   without it the labels wrap and clip inside the rounded frame once the main
   column drops under ~1100px.

   Rendered as a radiogroup rather than a row of buttons so a screen reader
   announces it as one control with a current choice. */
export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: readonly { readonly id: T; readonly label: string }[]
  onChange: (next: T) => void
  label: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="flex overflow-hidden rounded-[7px] border border-border bg-bg"
    >
      {options.map((option) => {
        const selected = option.id === value
        return (
          <button
            key={option.id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.id)}
            className={`flex-none whitespace-nowrap border-r border-border px-[13px] py-[9px] text-xs font-medium transition-colors last:border-r-0 ${
              selected ? 'bg-accent-subtle text-accent' : 'bg-bg text-text-muted hover:text-text'
            }`}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
