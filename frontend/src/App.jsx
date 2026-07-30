import { BrowserRouter, Routes, Route, Navigate, NavLink, Link } from 'react-router-dom'
import { IconStar } from '@tabler/icons-react'
import CandidateDashboardPage from './pages/CandidateDashboardPage'
import CategorySurveyPage from './pages/CategorySurveyPage'
import BasicInfoPage from './pages/BasicInfoPage'
import EducationPage from './pages/EducationPage'
import CapabilitiesPage from './pages/CapabilitiesPage'
import TaskHistoryPage from './pages/TaskHistoryPage'
import PremiumPage from './pages/PremiumPage'
import VacancyWorkshopPage from './pages/VacancyWorkshopPage'
import MatchPage from './pages/MatchPage'
import LoginPage from './pages/LoginPage'
import AdminPage from './pages/AdminPage'
import AdminDashboardPage from './pages/admin/AdminDashboardPage'
import PrivacyPolicyPage from './pages/PrivacyPolicyPage'
import TermsOfServicePage from './pages/TermsOfServicePage'
import { AuthProvider, useAuth } from './auth/AuthContext'
import logoIcon from './assets/logo-icon.svg'
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
  // No standalone "Survey" nav link -- each category now has its own dedicated
  // route (/candidate/survey/:categorySlug), reached only via the dashboard's
  // cards/Continue button. "Your profile" is the only real entry point: it's
  // what shows progress/framing/urgency before a candidate starts filling
  // anything in.
  const links = auth.role === 'candidate' ? [['/candidate', 'Your profile']]
    : auth.role === 'company' ? [['/vacancy', 'Vacancy workshop'], ['/match', 'Run match']]
    : [['/admin/dashboard', 'Dashboard'], ['/admin', 'Subscription tool']]

  return (
    <nav className="top-nav">
      <span className="brand"><img src={logoIcon} alt="" /><span>Launchino</span></span>
      {links.map(([to, label]) => (
        <NavLink key={to} to={to} end className={({ isActive }) => (isActive ? 'active' : '')}>{label}</NavLink>
      ))}
      {auth.role === 'candidate' && (
        <Link to="/candidate/premium" className="ll-premium-pill"><IconStar size={14} />Premium</Link>
      )}
      <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 13, color: 'rgba(255,255,255,0.72)' }}>{identity} ({auth.role})</span>
        <a href="#" onClick={(e) => { e.preventDefault(); logout() }} style={{ color: '#fff' }}>Log out</a>
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
      <Route path="/candidate" element={<RequireRole role="candidate"><AuthedLayout><CandidateDashboardPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/survey/basic-info" element={<RequireRole role="candidate"><AuthedLayout><BasicInfoPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/survey/education" element={<RequireRole role="candidate"><AuthedLayout><EducationPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/survey/capabilities" element={<RequireRole role="candidate"><AuthedLayout><CapabilitiesPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/survey/task-history" element={<RequireRole role="candidate"><AuthedLayout><TaskHistoryPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/survey/:categorySlug" element={<RequireRole role="candidate"><AuthedLayout><CategorySurveyPage /></AuthedLayout></RequireRole>} />
      <Route path="/candidate/premium" element={<RequireRole role="candidate"><AuthedLayout><PremiumPage /></AuthedLayout></RequireRole>} />
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
