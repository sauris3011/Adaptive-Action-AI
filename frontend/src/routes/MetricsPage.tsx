import { KpiStrip } from '../components/Kpi/KpiStrip'

/* KPI page (FR-18).

   The section 9 metrics, split into what was measured by the eval and what this
   deployment has actually done. Kept on its own route rather than pinned to the
   copilot page: an operator working a dispute does not need a metrics banner
   above every recommendation, and a reviewer looking for evidence should not
   have to submit a dispute to find it. */

export function MetricsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-text">Metrics</h1>
        <p className="mt-1 text-sm text-text-muted">
          Product and technical KPIs against the targets in the PRD, plus what this deployment has
          decided so far.
        </p>
      </div>
      <KpiStrip />
    </div>
  )
}
