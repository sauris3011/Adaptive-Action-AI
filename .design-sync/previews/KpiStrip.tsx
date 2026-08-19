import './_api'
import { KpiStrip } from 'adaptive-action-copilot-ui'

/* Two rows with a real distinction: eval KPIs are quality measurements from the
   last run and carry their age; live counters are what this deployment has
   actually done. Fetches /api/kpi itself, so the card is backed by the stub. */

export function Default() {
  return <KpiStrip />
}
