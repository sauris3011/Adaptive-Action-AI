import { AlertTriangle, Database, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, type RuntimeSettings, type TelemetrySummary } from '../../lib/api'
import { Field } from '../ui/Field'
import { Toggle } from '../ui/Toggle'

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

  useEffect(() => {
    if (!open) return
    setError(null)
    setSaved(false)
    api
      .settings()
      .then((s) => {
        setSettings(s)
        const parts = splitUrl(s.gateway_url)
        setBase(parts.base)
        setPort(parts.port)
      })
      .catch((e) => setError(String(e.message ?? e)))
  }, [open])

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    if (open) window.addEventListener('keydown', onEsc)
    return () => window.removeEventListener('keydown', onEsc)
  }, [open, onClose])

  const persist = async (patch: Parameters<typeof api.updateSettings>[0]) => {
    setSaving(true)
    setError(null)
    try {
      setSettings(await api.updateSettings(patch))
      setSaved(true)
      window.setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setSaving(false)
    }
  }

  const saveGateway = () => {
    const url = port ? `${base}:${port}` : base
    void persist({ gateway_url: url, ...(apiKey ? { gateway_api_key: apiKey } : {}) })
    setApiKey('')
  }

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
              <button type="button" className="btn-primary" onClick={saveGateway} disabled={saving}>
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

          <section className="space-y-2 border-t border-border pt-5">
            <h3 className="label-eyebrow">Model routing</h3>
            <dl className="space-y-1.5 text-sm">
              {Object.entries(settings?.models ?? {}).map(([role, alias]) => (
                <div key={role} className="flex justify-between gap-3">
                  <dt className="text-text-muted capitalize">{role}</dt>
                  <dd className="font-mono text-xs text-text">{alias}</dd>
                </div>
              ))}
            </dl>
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
