import { Field } from 'adaptive-action-copilot-ui'

/* Labelled text input. The label is an eyebrow above the control and the hint
   sits below it; both are part of the component, not the caller's layout. */

export function Default() {
  return <Field label="Gateway URL" defaultValue="http://localhost" placeholder="http://localhost" />
}

export function WithHint() {
  return (
    <Field
      label="API key / password"
      type="password"
      defaultValue="sk-local-gateway-admin-key"
      hint="Write-only. The backend never echoes the key back."
    />
  )
}

export function Stacked() {
  return (
    <div className="max-w-sm space-y-4">
      <Field label="Transaction ID" defaultValue="TXN-9002" />
      <Field label="Customer ID" placeholder="Optional" />
      <Field label="Port" inputMode="numeric" defaultValue="8787" hint="Must be above 1024." />
    </div>
  )
}

export function Disabled() {
  return <Field label="Case reference" defaultValue="CASE-2026-0431" disabled hint="Assigned on approval." />
}
