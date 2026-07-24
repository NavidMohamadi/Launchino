import { useState } from 'react'
import * as api from '../api'

const SUBSCRIPTION_STATES = ['none', 'active', 'expired']

export default function AdminPage() {
  const [talentId, setTalentId] = useState('')
  const [subscription, setSubscription] = useState('active')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setResult(null)
    try {
      const updated = await api.updateCandidateSubscription(talentId, { job_discovery_subscription: subscription })
      setResult(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <h1>Admin</h1>
      <div className="card">
        <h2>Set a candidate's job-discovery subscription</h2>
        <form onSubmit={handleSubmit}>
          <label className="field">Candidate (talent) ID
            <input value={talentId} onChange={(e) => setTalentId(e.target.value)} required />
          </label>
          <label className="field">Subscription state
            <select value={subscription} onChange={(e) => setSubscription(e.target.value)}>
              {SUBSCRIPTION_STATES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <button type="submit" disabled={submitting}>{submitting ? 'Updating...' : 'Update subscription'}</button>
        </form>
        {error && <p className="hint-error">{error}</p>}
        {result && (
          <p className="hint-success">
            {result.full_name}'s subscription is now <strong>{result.job_discovery_subscription}</strong>.
          </p>
        )}
      </div>
    </div>
  )
}
