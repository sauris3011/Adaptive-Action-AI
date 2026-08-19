/* Nothing-found state that suggests the next move.

   The hint is the point: an empty result on a look-up is usually a scope
   problem, and saying so is cheaper than making the operator guess which of the
   two controls was wrong. */
export function EmptyState({
  title,
  hint,
  action,
}: {
  title: React.ReactNode
  hint?: React.ReactNode
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="px-4 py-[34px] text-center">
      <div className="text-[13.5px] text-text">{title}</div>
      {hint && <div className="mt-1.5 text-xs leading-relaxed text-text-muted">{hint}</div>}
      {action && (
        <button type="button" onClick={action.onClick} className="btn-ghost mt-3 text-xs">
          {action.label}
        </button>
      )}
    </div>
  )
}
