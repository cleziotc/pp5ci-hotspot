import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layouts/AppShell'
import AboutPage from './pages/AboutPage'
import DashboardPage from './pages/DashboardPage'
import DiagnosticsPage from './pages/DiagnosticsPage'
import SettingsPage from './pages/SettingsPage'
import StatisticsPage from './pages/StatisticsPage'
import UpdatesPage from './pages/UpdatesPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/statistics" element={<StatisticsPage />} />
        <Route path="/diagnostics" element={<DiagnosticsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/updates" element={<UpdatesPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
