import { BrowserRouter, Routes, Route, Navigate, NavLink } from 'react-router-dom'
import CandidateSurveyPage from './pages/CandidateSurveyPage'
import VacancyWorkshopPage from './pages/VacancyWorkshopPage'
import MatchPage from './pages/MatchPage'
import LoginPage from './pages/LoginPage'
import AdminPage from './pages/AdminPage'
import AdminDashboardPage from './pages/admin/AdminDashboardPage'
import PrivacyPolicyPage from './pages/PrivacyPolicyPage'
import TermsOfServicePage from './pages/TermsOfServicePage'
import { AuthProvider, useAuth } from './auth/AuthContext'
import './App.css'

const DEFAULT_PATH_BY_ROLE = { candidate: '/candidate', company: '/vacancy', admin: '/admin/dashboard' }

// Real, URL-based gating: a non-admin (or logged-out visitor) typing
// /admin/dashboard directly gets redirected away, not just shown different
// content at the same URL -- this is why react-router-dom was added in this
// phase (the app had no client-side router before).
function RequireRole({ role, children }) {
  const { auth } = useAuth()
  if (!auth) return <Navigate to="/login" replace />
  if (auth.role !== role) return <Navigate to={DEFAULT_PATH_BY_ROLE[auth.role] || '/login'} replace />
  return children
}

function RootRedirect() {
  const { auth } = useAuth()
  return <Navigate to={auth ? (DEFAULT_PATH_BY_ROLE[auth.role] || '/login') : '/login'} replace />
}

function TopNav() {
  const { auth, logout } = useAuth()
  const identity = auth.role === 'candidate' ? auth.profile?.full_name
    : auth.role === 'company' ? auth.profile?.display_name
    : 'Admin'
  const links = auth.role === 'candidate' ? [['/candidate', 'Candidate survey']]
    : auth.role === 'company' ? [['/vacancy', 'Vacancy workshop'], ['/match', 'Run match']]
    : [['/admin/dashboard', 'Dashboard'], ['/admin', 'Subscription tool']]

  return (
    <nav className="top-nav">
      {links.map(([to, label]) => (
        <NavLink key={to} to={to} className={({ isActive }) => (isActive ? 'active' : '')}>{label}</NavLink>
      ))}
      <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 13, color: '#666' }}>{identity} ({auth.role})</span>
        <a href="#" onClick={(e) => { e.preventDefault(); logout() }}>Log out</a>
      </span>
    </nav>
  )
}

function AuthedLayout({ children }) {
  return (
    <div>
      <TopNav />
      {children}
    </div>
  )
}

function AppRoutes() {
  const { auth } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={auth ? <Navigate to={DEFAULT_PATH_BY_ROLE[auth.role] || '/login'} replace /> : <LoginPage />} />
      <Route path="/privacy" element={<PrivacyPolicyPage />} />
      <Route path="/terms" element={<TermsOfServicePage />} />
      <Route path="/candidate" element={<RequireRole role="candidate"><AuthedLayout><CandidateSurveyPage /></AuthedLayout></RequireRole>} />
      <Route path="/vacancy" element={<RequireRole role="company"><AuthedLayout><VacancyWorkshopPage /></AuthedLayout></RequireRole>} />
      <Route path="/match" element={<RequireRole role="company"><AuthedLayout><MatchPage /></AuthedLayout></RequireRole>} />
      <Route path="/admin" element={<RequireRole role="admin"><AuthedLayout><AdminPage /></AuthedLayout></RequireRole>} />
      <Route path="/admin/dashboard" element={<RequireRole role="admin"><AuthedLayout><AdminDashboardPage /></AuthedLayout></RequireRole>} />
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
