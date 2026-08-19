import { useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppHeader } from './components/Header/AppHeader'
import { SettingsDrawer } from './components/SettingsDrawer/SettingsDrawer'
import { useTelemetry } from './lib/useTelemetry'
import { CopilotPage } from './routes/CopilotPage'
import { GroundingPage } from './routes/GroundingPage'
import { MetricsPage } from './routes/MetricsPage'

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
      <main className="mx-auto max-w-[1400px] px-4 py-8 sm:px-6">
        <Routes>
          <Route path="/" element={<CopilotPage />} />
          <Route path="/metrics" element={<MetricsPage />} />
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
