import { useState } from 'react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import logoIcon from '../assets/logo-icon.svg'
import './LoginPage.css'

const ROLES = [
  { key: 'candidate', label: 'Candidate' },
  { key: 'company', label: 'Company' },
  { key: 'admin', label: 'Admin' },
]

const HERO_COPY = {
  candidate: {
    word: 'script',
    headline: 'Launch your career!',
    motto: null,
    sub: 'Get to know yourself better, and let real companies discover you — free, and at your own pace.',
    showList: true,
  },
  company: {
    word: 'sans',
    headline: 'Find your next great hire.',
    motto: null,
    sub: 'Post roles, search verified candidate profiles, and reach people who are ready to move.',
    showList: false,
  },
  admin: {
    word: 'sans',
    headline: 'Manage Launchino with confidence.',
    motto: null,
    sub: 'Oversight tools for accounts, listings, and platform health.',
    showList: false,
  },
}

export default function LoginPage() {
  const { login } = useAuth()
  const [role, setRole] = useState('candidate')
  const [mode, setMode] = useState('login') // 'login' | 'register' (admin has no register mode)
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [legalName, setLegalName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [websiteDomain, setWebsiteDomain] = useState('')
  const [consent, setConsent] = useState(false)

  function selectRole(nextRole) {
    setRole(nextRole)
    setMode('login')
    setError(null)
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (role === 'candidate') {
        const result = mode === 'register'
          ? await api.createCandidate({ full_name: fullName, email, password, data_processing_consent: consent })
          : await api.loginCandidate(email, password)
        login('candidate', result.access_token, result.candidate)
      } else if (role === 'company') {
        const result = mode === 'register'
          ? await api.createCompany({
              legal_name: legalName, display_name: displayName, website_domain: websiteDomain,
              contact_email: email, password, data_processing_consent: consent,
            })
          : await api.loginCompany(email, password)
        login('company', result.access_token, result.company)
      } else {
        const result = await api.loginAdmin(email, password)
        login('admin', result.access_token, null)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const hero = HERO_COPY[role]

  return (
    <div className="ll-page">
      <div className="ll-body">
      <div className="ll-hero">
        <div className="ll-hero-mark">
          <img src={logoIcon} alt="" width="72" height="72" />
          <span className={hero.word === 'script' ? 'll-wordmark ll-wordmark-script' : 'll-wordmark ll-wordmark-sans'}>
            Launchino
          </span>
        </div>
        <h1 className="ll-headline">{hero.headline}</h1>
        {hero.showList && <p className="ll-motto">&ldquo;<span style={{ fontWeight: 'normal' }}>You can be anything you want<br />&mdash; you just need the</span> right resources.&rdquo;</p>}
        <p className="ll-sub">{hero.sub}</p>
        {hero.showList && (
          <ul className="ll-checklist">
            <li>Show who you really are, not just your CV</li>
            <li>Discover what actually fits you, from how you work to what drives you</li>
            <li>Want us to actively find jobs for you? Sure, whenever you're ready!</li>
          </ul>
        )}
      </div>

      <div className="ll-form-wrap">
        <div className="ll-card">
          <div className="ll-role-tabs" role="tablist">
            {ROLES.map((r) => (
              <label key={r.key} className={role === r.key ? 'll-role-tab ll-role-tab-active' : 'll-role-tab'}>
                <input type="radio" name="role" checked={role === r.key} onChange={() => selectRole(r.key)} />
                {r.label}
              </label>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="ll-form">
            {mode === 'register' && role === 'candidate' && (
              <label className="ll-field">
                <span>Full name</span>
                <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
              </label>
            )}
            {mode === 'register' && role === 'company' && (
              <>
                <label className="ll-field">
                  <span>Legal name</span>
                  <input value={legalName} onChange={(e) => setLegalName(e.target.value)} required />
                </label>
                <label className="ll-field">
                  <span>Display name</span>
                  <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
                </label>
                <label className="ll-field">
                  <span>Website domain</span>
                  <input value={websiteDomain} onChange={(e) => setWebsiteDomain(e.target.value)} placeholder="example.com" required />
                </label>
              </>
            )}
            <label className="ll-field">
              <span>{role === 'company' ? 'Contact email' : 'Email'}</span>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </label>
            <label className="ll-field">
              <span>Password</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </label>
            {mode === 'register' && (
              <label className="ll-consent">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
                <span>
                  I agree to the <a href="/privacy" target="_blank" rel="noopener noreferrer">Privacy Policy</a> and{' '}
                  <a href="/terms" target="_blank" rel="noopener noreferrer">Terms of Service</a>.
                </span>
              </label>
            )}

            <button type="submit" className="ll-submit" disabled={submitting}>
              {submitting ? 'Please wait…' : mode === 'register' ? 'Register' : 'Sign in'}
            </button>
            {role !== 'admin' && (
              <button
                type="button"
                className="ll-switch-mode"
                onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}
              >
                {mode === 'login' ? 'Need an account? Register' : 'Have an account? Log in'}
              </button>
            )}
          </form>
          {error && <p className="ll-error">{error}</p>}
        </div>
      </div>
      </div>
      <div className="ll-powered-by">Powered by SHEXON B.V.</div>
    </div>
  )
}
