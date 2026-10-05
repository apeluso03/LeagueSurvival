import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { HistoryPage } from './pages/HistoryPage'
import { PoolPage } from './pages/PoolPage'
import { SettingsPage } from './pages/SettingsPage'
import { StatsPage } from './pages/StatsPage'
import { WheelsPage } from './pages/WheelsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<WheelsPage />} />
        <Route path="pool" element={<PoolPage />} />
        <Route path="stats" element={<StatsPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
