import { useEffect, useState } from 'react'
import * as api from '../../api'

export default function SponsorReviewTab() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [resolvingId, setResolvingId] = useState(null)
  const [resolveError, setResolveError] = useState(null)

  useEffect(() => {
    api.getSponsorReview().then(setItems).catch((err) => setError(err.message))
  }, [])

  async function resolve(vacancyId, decision) {
    setResolvingId(vacancyId)
    setResolveError(null)
    try {
      await api.resolveSponsorReview(vacancyId, decision)
      setItems((prev) => prev.filter((item) => item.vacancy_id !== vacancyId))
    } catch (err) {
      setResolveError(err.message)
    } finally {
      setResolvingId(null)
    }
  }

  if (error) return <p className="hint-error">Could not load sponsor review queue: {error}</p>
  if (!items) return <p>Loading...</p>

  return (
    <div>
      <h2>Sponsor-match review</h2>
      {resolveError && <p className="hint-error">{resolveError}</p>}
      {items.length === 0 && (
        <div className="unmapped-terms">
          No items -- sponsor-registry wiring is deferred, see PROJECT_NOTES.md.
          Nothing in the real ingestion pipeline currently computes a sponsor-match
          signal, so this queue is expected to be empty until that's wired up.
        </div>
      )}
      {items.map((item) => (
        <div key={item.vacancy_id} className="review-item">
          <p style={{ margin: 0 }}><strong>{item.title}</strong> at {item.company_name}</p>
          <p style={{ margin: '4px 0', fontSize: 13, color: '#666' }}>
            Matched organisation: {item.sponsorship_signal.matched_organisation_name || 'n/a'}
            {' -- '}method: {item.sponsorship_signal.match_method}
            {item.sponsorship_signal.match_confidence != null
              ? ` (${(item.sponsorship_signal.match_confidence * 100).toFixed(0)}% confidence)` : ''}
          </p>
          <p style={{ margin: '4px 0', fontSize: 13 }}>{item.sponsorship_signal.note}</p>
          <div className="review-item-actions">
            <button type="button" disabled={resolvingId === item.vacancy_id}
              onClick={() => resolve(item.vacancy_id, 'confirm')}>
              Confirm
            </button>
            <button type="button" className="secondary reject" disabled={resolvingId === item.vacancy_id}
              onClick={() => resolve(item.vacancy_id, 'reject')}>
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
