export function Select({
  label,
  hint,
  children,
  ...props
}: { label: string; hint?: string } & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <label className="block space-y-1.5">
      <span className="label-eyebrow block">{label}</span>
      <select className="field font-mono text-xs" {...props}>
        {children}
      </select>
      {hint && <span className="block text-xs text-text-subtle">{hint}</span>}
    </label>
  )
}
