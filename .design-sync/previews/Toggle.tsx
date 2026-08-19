import { useState } from 'react'
import { Toggle } from 'adaptive-action-copilot-ui'

/* The switch used throughout the settings drawer. `tone="danger"` marks a
   toggle whose ON state is the unsafe one (disabling TLS verification). */

export function Default() {
  const [on, setOn] = useState(true)
  return (
    <div className="flex items-center gap-3">
      <Toggle id="t-default" checked={on} onChange={setOn} label="Use the LLM gateway" />
      <span className="text-sm text-text">Use the LLM gateway</span>
    </div>
  )
}

export function OffAndOn() {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Toggle id="t-off" checked={false} onChange={() => {}} label="Off" />
        <span className="text-sm text-text-muted">Off</span>
      </div>
      <div className="flex items-center gap-3">
        <Toggle id="t-on" checked onChange={() => {}} label="On" />
        <span className="text-sm text-text-muted">On</span>
      </div>
    </div>
  )
}

export function DangerTone() {
  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-4">
        <label htmlFor="t-ssl" className="text-sm text-text">
          Disable SSL verification
          <span className="mt-0.5 block text-xs text-text-muted">
            For the intercepting corporate proxy.
          </span>
        </label>
        <Toggle id="t-ssl" checked onChange={() => {}} label="Disable SSL verification" tone="danger" />
      </div>
    </div>
  )
}
