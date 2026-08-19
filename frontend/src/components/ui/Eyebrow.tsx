/* Section label, 9.5px mono and widely tracked.

   Deliberately smaller and quieter than the existing `.label-eyebrow`: on the
   record screens an eyebrow sits directly above a value it must not compete
   with, and monospace is what makes those screens read as a record system
   rather than a web app. */
export function Eyebrow({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`font-mono text-[9.5px] font-medium uppercase tracking-[0.08em] text-text-subtle ${className}`}
    >
      {children}
    </div>
  )
}
