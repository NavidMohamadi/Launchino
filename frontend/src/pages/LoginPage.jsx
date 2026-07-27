import { useState } from 'react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'

const ROLES = [
  { key: 'candidate', label: 'Candidate' },
  { key: 'company', label: 'Company' },
  { key: 'admin', label: 'Admin' },
]

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

  return (
    <div>
      <h1>Log in</h1>
      <div className="card">
        <div className="tri-state-toggle" style={{ marginBottom: 16 }}>
          {ROLES.map((r) => (
            <label key={r.key} className={role === r.key ? 'active' : ''}>
              <input type="radio" name="role" checked={role === r.key} onChange={() => selectRole(r.key)} />
              {r.label}
            </label>
          ))}
        </div>

        <form onSubmit={handleSubmit}>
          {mode === 'register' && role === 'candidate' && (
            <label className="field">Full name
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            </label>
          )}
          {mode === 'register' && role === 'company' && (
            <>
              <label className="field">Legal name
                <input value={legalName} onChange={(e) => setLegalName(e.target.value)} required />
              </label>
              <label className="field">Display name
                <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
              </label>
              <label className="field">Website domain
                <input value={websiteDomain} onChange={(e) => setWebsiteDomain(e.target.value)} placeholder="example.com" required />
              </label>
            </>
          )}
          <label className="field">{role === 'company' ? 'Contact email' : 'Email'}
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </label>
          <label className="field">Password
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </label>
          {mode === 'register' && (
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginTop: 8, fontSize: 14 }}>
              <input
                type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} required
                style={{ marginTop: 3 }}
              />
              I agree to my data being processed as described in the privacy policy.
            </label>
          )}

          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button type="submit" disabled={submitting}>
              {submitting ? 'Please wait...' : mode === 'register' ? 'Register' : 'Log in'}
            </button>
            {role !== 'admin' && (
              <button type="button" className="secondary" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(null) }}>
                {mode === 'login' ? 'Need an account? Register' : 'Have an account? Log in'}
              </button>
            )}
          </div>
        </form>
        {error && <p className="hint-error">{error}</p>}
      </div>
    </div>
  )
}
