import { useEffect, useState } from 'react'
import * as api from '../../api'

const PLAN_LABELS = { one_month: '1 month (EUR 25)', three_month: '3 months (EUR 50)' }

export default function PremiumRequestsTab() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [resolvingId, setResolvingId] = useState(null)
  const [resolveError, setResolveError] = useState(null)
  const [confirmations, setConfirmations] = useState({})

  useEffect(() => {
    api.getPremiumRequestQueue().then(setItems).catch((err) => setError(err.message))
  }, [])

  async function resolve(item, decision) {
    setResolvingId(item.request_id)
    setResolveError(null)
    try {
      const result = await api.resolvePremiumRequest(item.request_id, decision)
      setItems((prev) => prev.filter((row) => row.request_id !== item.request_id))
      if (decision === 'approve' && result.talent) {
        setConfirmations((prev) => ({
          ...prev,
          [item.request_id]: `Approved -- ${item.full_name}'s subscription is now `
            + `${result.talent.job_discovery_subscription} (source: ${result.talent.subscription_source}, `
            + `expires ${new Date(result.talent.subscription_expires_at).toLocaleDateString()}).`,
        }))
      }
    } catch (err) {
      setResolveError(err.message)
    } finally {
      setResolvingId(null)
    }
  }

  if (error) return <p className="hint-error">Could not load Premium requests: {error}</p>
  if (!items) return <p>Loading...</p>

  return (
    <div>
      <h2>Premium requests</h2>
      {resolveError && <p className="hint-error">{resolveError}</p>}
      {Object.values(confirmations).map((msg, i) => <p key={i} className="hint-success">{msg}</p>)}
      {items.length === 0 && <p>No pending Premium requests.</p>}
      {items.map((item) => (
        <div key={item.request_id} className="review-item">
          <p style={{ margin: 0 }}><strong>{item.full_name}</strong> ({item.email})</p>
          <p style={{ margin: '4px 0', fontSize: 13, color: 'var(--ll-neutral-600)' }}>
            Plan: {PLAN_LABELS[item.plan] || item.plan} -- requested {new Date(item.requested_at).toLocaleString()}
          </p>
          <div className="review-item-actions">
            <button type="button" disabled={resolvingId === item.request_id}
              onClick={() => resolve(item, 'approve')}>
              Approve
            </button>
            <button type="button" className="secondary reject" disabled={resolvingId === item.request_id}
              onClick={() => resolve(item, 'deny')}>
              Deny
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
