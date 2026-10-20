import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { InvitePage, LoginPage, RequireAuth, SetupPage, SignupPage, StartGroupPage } from './pages/AuthPages'
import { HistoryPage } from './pages/HistoryPage'
import { LandingPage } from './pages/LandingPage'
import { LegalPage } from './pages/LegalPage'
import { LivePage } from './pages/LivePage'
import { OverlayPage } from './pages/OverlayPage'
import { PlayerPage } from './pages/PlayerPage'
import { PoolPage } from './pages/PoolPage'
import { RecapPage } from './pages/RecapPage'
import { SettingsPage } from './pages/SettingsPage'
import { ShopPage } from './pages/ShopPage'
import { StatsPage } from './pages/StatsPage'
import { TrophiesPage } from './pages/TrophiesPage'
import { WheelsPage } from './pages/WheelsPage'
import { WrappedPage } from './pages/WrappedPage'

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route path="setup" element={<SetupPage />} />
      <Route path="invite/:token" element={<InvitePage />} />
      <Route path="signup" element={<SignupPage />} />
      <Route path="legal" element={<LegalPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<LandingPage />} />
        <Route path="groups/new" element={<StartGroupPage />} />
        <Route path="overlay" element={<OverlayPage />} />
        <Route element={<Layout />}>
          <Route path="wheels" element={<WheelsPage />} />
          <Route path="live" element={<LivePage />} />
          <Route path="pool" element={<PoolPage />} />
          <Route path="shop" element={<ShopPage />} />
          <Route path="stats" element={<StatsPage />} />
          <Route path="trophies" element={<TrophiesPage />} />
          <Route path="wrapped" element={<WrappedPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="players/:id" element={<PlayerPage />} />
          <Route path="runs/:id/recap" element={<RecapPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
