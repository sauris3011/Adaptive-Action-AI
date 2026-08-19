/* Confirmation that something was written somewhere the operator cannot see.

   Success-toned and dismissible rather than a toast: opening a case or handing
   a transaction to the copilot has a consequence in the case trace, and a
   message about it should stay on screen until it is read. */
export function NoticeStrip({
  children,
  onDismiss,
}: {
  children: React.ReactNode
  onDismiss?: () => void
}) {
  return (
    <div
      role="status"
      className="flex items-center gap-[11px] rounded-lg border border-success bg-success-subtle px-[14px] py-3"
    >
      <span className="h-[9px] w-[9px] flex-none rounded-full bg-success" aria-hidden="true" />
      <span className="text-[13px] leading-normal text-text">{children}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="ml-auto flex-none text-xs font-medium text-success hover:underline"
        >
          Dismiss
        </button>
      )}
    </div>
  )
}
