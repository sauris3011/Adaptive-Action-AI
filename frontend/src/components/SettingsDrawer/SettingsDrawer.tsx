import { AlertTriangle, Database, RefreshCw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { api, type ModelCatalog, type RuntimeSettings, type TelemetrySummary } from '../../lib/api'
import { Field } from '../ui/Field'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'

/* Role order is presentational only; the backend owns the authoritative set and
   the drawer renders whatever roles it reports. */
const ROLE_ORDER = ['triage', 'digest', 'reason', 'embed']

const ROLE_HINTS: Record<string, string> = {
  triage: 'Cheap, fast. Classification and routing.',
  digest: 'Mid-tier. Summarisation and extraction.',
  reason: 'Most capable. Grounded reconciliation and the approval gate.',
  embed: 'Embeddings for retrieval.',
}

const NOT_SELECTED = ''

/* Settings drawer (FR-14).
   The master prompt asks for URL, Port and key as separate inputs, so the UI
   splits them and recomposes into the single gateway_url the backend stores. */

function splitUrl(url: string): { base: string; port: string } {
  try {
    const parsed = new URL(url)
    const port = parsed.port || (parsed.protocol === 'https:' ? '443' : '80')
    parsed.port = ''
    return { base: parsed.origin.replace(/:\d+$/, ''), port }
  } catch {
    return { base: url, port: '' }
  }
}

export function SettingsDrawer({
  open,
  onClose,
  telemetry,
}: {
  open: boolean
  onClose: () => void
  telemetry: TelemetrySummary | null
}) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null)
  const [base, setBase] = useState('')
  const [port, setPort] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  /* Model routing. The catalogue is discovered from the gateway - the UI ships
     no hardcoded model list and nothing is selected until the user picks. */
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null)
  const [probing, setProbing] = useState(false)
  const [probeError, setProbeError] = useState<string | null>(null)
  const [draftModels, setDraftModels] = useState<Record<string, string>>({})

  const probe = useCallback(async () => {
    setProbing(true)
    setProbeError(null)
    try {
      setCatalog(await api.modelCatalog())
    } catch (e) {
      setCatalog(null)
      setProbeError(String((e as Error).message))
    } finally {
      setProbing(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    setError(null)
    setSaved(false)
    api
      .settings()
      .then((s) => {
        setSettings(s)
        setDraftModels(s.models)
        const parts = splitUrl(s.gateway_url)
        setBase(parts.base)
        setPort(parts.port)
      })
      .catch((e) => setError(String(e.message ?? e)))
    void probe()
  }, [open, probe])

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    if (open) window.addEventListener('keydown', onEsc)
    return () => window.removeEventListener('keydown', onEsc)
  }, [open, onClose])

  const persist = async (patch: Parameters<typeof api.updateSettings>[0]) => {
    setSaving(true)
    setError(null)
    try {
      const next = await api.updateSettings(patch)
      setSettings(next)
      setDraftModels(next.models)
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setSaving(false)
    }
  }

  const saveGateway = async () => {
    const url = port ? `${base}:${port}` : base
    await persist({ gateway_url: url, ...(apiKey ? { gateway_api_key: apiKey } : {}) })
    setApiKey('')
    // The catalogue belongs to the old gateway until it is re-probed.
    setCatalog(null)
    void probe()
  }

  const chooseModel = (role: string, alias: string) => {
    setDraftModels((prev) => ({ ...prev, [role]: alias }))
    void persist({ models: { [role]: alias } })
  }

  const roles = Object.keys(settings?.models ?? {}).sort(
    (a, b) => ROLE_ORDER.indexOf(a) - ROLE_ORDER.indexOf(b),
  )

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-overlay/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-label="Settings"
        className="relative flex h-full w-full max-w-md flex-col overflow-y-auto
                   border-l border-border bg-surface shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-text">Settings</h2>
          <button type="button" onClick={onClose} className="btn-ghost" aria-label="Close settings">
            <X size={15} />
          </button>
        </header>

        <div className="space-y-6 p-5">
          {error && (
            <p className="rounded-md bg-danger-subtle px-3 py-2 text-sm text-danger">{error}</p>
          )}

          <section className="space-y-3">
            <h3 className="label-eyebrow">LiteLLM Gateway</h3>
            <Field
              label="Gateway URL"
              value={base}
              onChange={(e) => setBase(e.target.value)}
              placeholder="http://localhost"
            />
            <Field
              label="Port"
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="4000"
              inputMode="numeric"
            />
            <Field
              label="API key / password"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={settings?.gateway_api_key_set ? '•••••••• (set)' : 'not set'}
              hint="Write-only. The backend never echoes the key back."
            />
            <div className="flex items-center gap-3">
              <button type="button" className="btn-primary" onClick={() => void saveGateway()} disabled={saving}>
                {saving ? 'Saving…' : 'Apply'}
              </button>
              {saved && <span className="text-sm text-success">Applied</span>}
            </div>
          </section>

          <section className="space-y-3 border-t border-border pt-5">
            <h3 className="label-eyebrow">Transport security</h3>
            <div className="flex items-start justify-between gap-4">
              <label htmlFor="ssl-toggle" className="text-sm text-text">
                Disable SSL verification
                <span className="mt-0.5 block text-xs text-text-muted">
                  For the intercepting corporate proxy.
                </span>
              </label>
              <Toggle
                id="ssl-toggle"
                checked={settings ? !settings.ssl_verify : false}
                onChange={(disabled) => void persist({ ssl_verify: !disabled })}
                label="Disable SSL verification"
                tone="danger"
              />
            </div>
            {settings?.tls_warning && (
              <p className="flex gap-2 rounded-md bg-danger-subtle px-3 py-2 text-xs text-danger">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>{settings.tls_warning}</span>
              </p>
            )}
          </section>

          <section className="space-y-2 border-t border-border pt-5">
            <h3 className="label-eyebrow">Cache</h3>
            <dl className="grid grid-cols-3 gap-2 text-sm">
              <div className="card p-3">
                <dt className="text-xs text-text-subtle">Hits</dt>
                <dd className="tnum font-medium text-success">{telemetry?.cache_hits ?? 0}</dd>
              </div>
              <div className="card p-3">
                <dt className="text-xs text-text-subtle">Misses</dt>
                <dd className="tnum font-medium text-text">{telemetry?.cache_misses ?? 0}</dd>
              </div>
              <div className="card p-3">
                <dt className="text-xs text-text-subtle">Hit ratio</dt>
                <dd className="tnum font-medium text-text">
                  {((telemetry?.cache_hit_ratio ?? 0) * 100).toFixed(0)}%
                </dd>
              </div>
            </dl>
          </section>

          <section className="space-y-3 border-t border-border pt-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="label-eyebrow">Model routing</h3>
              <button
                type="button"
                className="btn-ghost text-xs"
                onClick={() => void probe()}
                disabled={probing}
              >
                <RefreshCw size={13} className={probing ? 'animate-spin' : undefined} />
                {probing ? 'Probing…' : catalog ? 'Re-probe' : 'Probe gateway'}
              </button>
            </div>

            {probeError && (
              <p className="flex gap-2 rounded-md bg-danger-subtle px-3 py-2 text-xs text-danger">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>{probeError}</span>
              </p>
            )}

            {catalog && (
              <p className="text-xs text-text-subtle">
                {catalog.models.length} model{catalog.models.length === 1 ? '' : 's'} offered by{' '}
                <span className="font-mono">{catalog.gateway_url}</span>
              </p>
            )}

            {(settings?.unconfigured_roles.length ?? 0) > 0 && (
              <p className="rounded-md bg-warning-subtle px-3 py-2 text-xs text-warning">
                No model selected for {settings?.unconfigured_roles.join(', ')}. Calls on those
                roles will fail until one is chosen.
              </p>
            )}

            <div className="space-y-3">
              {roles.map((role) => {
                const selected = draftModels[role] ?? NOT_SELECTED
                /* Embedding roles lead with the ids that look like embedding
                   models, but every id stays selectable - the gateway does not
                   report capability, so the hint must never become a filter. */
                const options =
                  role === 'embed' && catalog
                    ? [
                        ...catalog.embedding_models,
                        ...catalog.models.filter((m) => !catalog.embedding_models.includes(m)),
                      ]
                    : (catalog?.models ?? [])
                /* A model set via MODEL_* but absent from the catalogue would
                   otherwise silently vanish from the dropdown. */
                const withCurrent =
                  selected && !options.includes(selected) ? [selected, ...options] : options

                return (
                  <Select
                    key={role}
                    label={role}
                    hint={ROLE_HINTS[role]}
                    value={selected}
                    disabled={saving || (!catalog && !selected)}
                    onChange={(e) => chooseModel(role, e.target.value)}
                  >
                    <option value={NOT_SELECTED}>
                      {catalog ? '— select a model —' : '— probe the gateway first —'}
                    </option>
                    {withCurrent.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </Select>
                )
              })}
            </div>

            <p className="flex items-center gap-2 pt-2 text-xs text-text-subtle">
              <Database size={13} />
              Knowledge graph: <span className="font-medium text-text">{settings?.graph_backend}</span>
            </p>
          </section>
        </div>
      </aside>
    </div>
  )
}
