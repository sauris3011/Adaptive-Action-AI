import './_api'
import { SettingsDrawer } from 'adaptive-action-copilot-ui'
import { TELEMETRY } from './_fixtures'

/* The full settings surface: gateway connection, the transport-security bypass
   with its warning banner, cache counters and model routing. Shown in its
   gateway-disabled state, where the drawer explains the inert model dropdowns
   rather than looking broken.

   The drawer is a `fixed inset-0` overlay, so on its own the preview root has
   no measurable height and the card captures blank. The wrapper below sets a
   transform, which makes it a containing block for fixed descendants — the
   overlay is then laid out inside this box at a real size. */

function Stage({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="relative overflow-hidden rounded-lg border border-border bg-bg"
      style={{ height: 720, transform: 'translateZ(0)' }}
    >
      <div className="p-6">
        <p className="label-eyebrow">Settings drawer</p>
        <p className="mt-1 max-w-sm text-xs text-text-muted">
          Slides over the app from the right. Everything behind it stays mounted.
        </p>
      </div>
      {children}
    </div>
  )
}

export function Open() {
  return (
    <Stage>
      <SettingsDrawer open onClose={() => {}} telemetry={TELEMETRY} />
    </Stage>
  )
}
