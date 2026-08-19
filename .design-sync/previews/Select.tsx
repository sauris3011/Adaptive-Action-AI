import { Select } from 'adaptive-action-copilot-ui'

/* Labelled select. The control is monospaced — it is used almost entirely for
   model ids and other identifiers where character alignment matters. */

export function Default() {
  return (
    <Select label="reason" defaultValue="gemini-2.5-pro" hint="Most capable. Grounded reconciliation and the approval gate.">
      <option value="gemini-2.5-flash-lite">gemini-2.5-flash-lite</option>
      <option value="gemini-2.5-flash">gemini-2.5-flash</option>
      <option value="gemini-2.5-pro">gemini-2.5-pro</option>
    </Select>
  )
}

export function ModelRouting() {
  return (
    <div className="max-w-sm space-y-4">
      <Select label="triage" defaultValue="gemini-2.5-flash-lite" hint="Cheap, fast. Classification and routing.">
        <option>gemini-2.5-flash-lite</option>
      </Select>
      <Select label="digest" defaultValue="gemini-2.5-flash" hint="Mid-tier. Summarisation and extraction.">
        <option>gemini-2.5-flash</option>
      </Select>
      <Select label="embed" defaultValue="text-embedding-004" hint="Embeddings for retrieval.">
        <option>text-embedding-004</option>
      </Select>
    </div>
  )
}

export function Unselected() {
  return (
    <Select label="reason" defaultValue="" hint="Nothing routes to this role until a model is chosen.">
      <option value="">— probe the gateway first —</option>
    </Select>
  )
}
