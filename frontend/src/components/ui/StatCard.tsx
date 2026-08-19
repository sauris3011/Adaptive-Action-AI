import { Eyebrow } from './Eyebrow'

/* Eyebrow over a hairline card. The rails are built almost entirely from these,
   which is why the pairing is a component rather than repeated markup. */
export function StatCard({
  title,
  children,
  className = '',
}: {
  title?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className={className}>
      {title && <Eyebrow>{title}</Eyebrow>}
      <div className={`card px-[13px] py-3 ${title ? 'mt-2' : ''}`}>
        <div className="flex flex-col gap-1.5">{children}</div>
      </div>
    </div>
  )
}
