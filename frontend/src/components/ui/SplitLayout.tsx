/* Main column plus a fixed 344px rail, shared by the two record screens.

   The rail is fixed-width rather than fluid because everything in it is a
   key/value pair read against a column edge; a rail that reflows makes those
   edges move as the selection changes.

   It collapses under the main column at 1100px rather than at a named Tailwind
   breakpoint: 344px of rail plus a readable table is what actually stops
   fitting there, and `lg` (1024px) is early enough to waste a column of screen
   on a laptop. */
export function SplitLayout({ children, rail }: { children: React.ReactNode; rail: React.ReactNode }) {
  return (
    <div className="grid items-start min-[1100px]:grid-cols-[1fr_344px]">
      <div className="min-w-0 px-7 py-[26px]">{children}</div>
      <aside className="border-t border-border bg-surface px-[18px] py-[22px] min-[1100px]:min-h-[calc(100vh-56px)] min-[1100px]:border-l min-[1100px]:border-t-0">
        {rail}
      </aside>
    </div>
  )
}
