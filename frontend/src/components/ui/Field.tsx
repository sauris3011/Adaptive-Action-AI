export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block space-y-1.5">
      <span className="label-eyebrow block">{label}</span>
      <input className="field" {...props} />
      {hint && <span className="block text-xs text-text-subtle">{hint}</span>}
    </label>
  )
}
