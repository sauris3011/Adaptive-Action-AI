import { ThemeToggle } from 'adaptive-action-copilot-ui'

/* Self-contained: reads and writes the stored theme and sets data-theme on the
   document root, so it takes no props. */

export function Default() {
  return <ThemeToggle />
}

export function InAHeaderRow() {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-surface p-2">
      <ThemeToggle />
      <span className="text-xs text-text-subtle">Sits at the right edge of the app header.</span>
    </div>
  )
}
