import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppHeader } from './components/Header/AppHeader'
import { SettingsDrawer } from './components/SettingsDrawer/SettingsDrawer'
import { useTelemetry } from './lib/useTelemetry'
import { CopilotPage } from './routes/CopilotPage'
import { GroundingPage } from './routes/GroundingPage'
import { MetricsPage } from './routes/MetricsPage'
import { TransactionsPage } from './routes/TransactionsPage'

function Contained({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6">{children}</div>
}

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const { data: telemetry, offline } = useTelemetry()

  return (
    <div className="min-h-screen bg-bg">
      <AppHeader
        telemetry={telemetry}
        offline={offline}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {/* The record screens run edge-to-edge under the header with a
          full-height rail, so the centred container belongs to the routes that
          want it rather than to <main>. */}
      <main>
        <Routes>
          <Route path="/" element={<Contained><CopilotPage /></Contained>} />
          {/* A run id in the URL recovers that run from its checkpoint. This is
              what makes the durable approval gate reachable: the look-up screen
              opens a dispute, parks it here, and a reload still finds it. */}
          <Route path="/copilot/:runId" element={<Contained><CopilotPage /></Contained>} />
          <Route path="/metrics" element={<Contained><MetricsPage /></Contained>} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/grounding" element={<GroundingPage />} />
        </Routes>
      </main>
      <SettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        telemetry={telemetry}
      />
    </div>
  )
}
