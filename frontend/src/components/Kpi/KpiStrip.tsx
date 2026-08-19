import { Activity, CircleCheck, CircleX, FlaskConical } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, api, type Kpi, type KpiResponse } from '../../lib/api'

/* KPI strip (FR-18).

   Two rows with a real distinction between them, not a wall of numbers:

   * EVAL KPIs are quality measurements from the last run_eval.py, and carry
     their age. A stale number presented as live is worse than no number.
   * LIVE counters are what this deployment has actually done.

   When no eval has been run the strip says so and prints the command, rather
   than rendering zeros - an unrun eval must never read as a failed one. */

function KpiTile({ kpi }: { kpi: Kpi }) {
  return (
    <div className="card p-3" title={kpi.detail}>
      <div className="flex items-start justify-between gap-2">
        <p className="label-eyebrow">{kpi.name}</p>
        {kpi.pass ? (
          <CircleCheck size={13} className="shrink-0 text-success" />
        ) : (
          <CircleX size={13} className="shrink-0 text-danger" />
        )}
      </div>
      <p className={`tnum mt-1 text-lg font-semibold ${kpi.pass ? 'text-text' : 'text-danger'}`}>
        {kpi.value}
        <span className="ml-1 text-xs font-normal text-text-subtle">{kpi.unit}</span>
      </p>
      <p className="tnum mt-0.5 text-[11px] text-text-subtle">target {kpi.target}</p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-3">
      <p className="label-eyebrow">{label}</p>
      <p className="tnum mt-1 text-lg font-semibold text-text">{value}</p>
    </div>
  )
}

export function KpiStrip() {
  const [data, setData] = useState<KpiResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .kpis()
      .then(setData)
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)))
  }, [])

  if (error) {
    return <div className="card p-3 text-sm text-danger">{error}</div>
  }
  if (!data) {
    return <div className="card p-3 text-sm text-text-subtle">Loading KPIs.</div>
  }

  const { eval: report, live } = data

  return (
    <div className="space-y-4">
      <section>
        <header className="mb-2 flex flex-wrap items-center gap-2">
          <FlaskConical size={14} className="text-text-muted" />
          <h2 className="text-sm font-semibold text-text">Eval KPIs</h2>
          {report ? (
            <>
              <span className="text-xs text-text-subtle">
                {report.passed}/{report.cases} cases passed every check
              </span>
              <span className="text-xs text-text-subtle">
                - measured {report.age_hours < 1
                  ? 'less than an hour ago'
                  : `${report.age_hours.toFixed(0)}h ago`}
              </span>
              <span
                className={`ml-auto rounded px-2 py-0.5 text-[11px] font-medium ${
                  report.all_targets_met
                    ? 'bg-success-subtle text-success'
                    : 'bg-danger-subtle text-danger'
                }`}
              >
                {report.all_targets_met ? 'All targets met' : 'Targets missed'}
              </span>
            </>
          ) : (
            <span className="text-xs text-text-subtle">not yet run</span>
          )}
        </header>

        {report ? (
          <>
            <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {report.product_kpis.map((kpi) => (
                <KpiTile key={kpi.name} kpi={kpi} />
              ))}
            </div>
            <div className="mt-2 grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
              {report.technical_kpis.map((kpi) => (
                <KpiTile key={kpi.name} kpi={kpi} />
              ))}
            </div>
            <p className="mt-2 text-[11px] text-text-subtle">
              Baseline note: {report.assumed_baseline.note} The copilot-side numbers above are
              measured; the manual baseline they improve on is not.
            </p>
          </>
        ) : (
          <div className="card p-4">
            <p className="text-sm text-text-muted">
              No eval has been run in this deployment yet.
            </p>
            <pre className="mt-2 overflow-x-auto rounded bg-surface p-2 text-xs text-text">
              {data.eval_command}
            </pre>
            <p className="mt-2 text-[11px] text-text-subtle">
              The eval calls the real gateway and takes a few minutes, so it is not triggered from
              the UI.
            </p>
          </div>
        )}
      </section>

      <section>
        <header className="mb-2 flex items-center gap-2">
          <Activity size={14} className="text-text-muted" />
          <h2 className="text-sm font-semibold text-text">This deployment</h2>
        </header>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <Stat label="Cases decided" value={live.cases_decided} />
          <Stat label="Approval rate" value={`${live.approval_rate_pct}%`} />
          <Stat label="Avg latency" value={`${(live.avg_latency_ms / 1000).toFixed(1)}s`} />
          <Stat label="Max latency" value={`${(live.max_latency_ms / 1000).toFixed(1)}s`} />
          <Stat label="Avg confidence" value={live.avg_confidence.toFixed(2)} />
        </div>
        {Object.keys(live.by_outcome).length > 0 && (
          <p className="mt-2 text-[11px] text-text-subtle">
            {Object.entries(live.by_outcome)
              .map(([outcome, count]) => `${outcome.replace(/_/g, ' ')}: ${count}`)
              .join(' - ')}
          </p>
        )}
      </section>
    </div>
  )
}
