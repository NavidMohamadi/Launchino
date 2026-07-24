import { useEffect, useState } from 'react'
import * as api from '../../api'

export default function DedupReviewTab() {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [resolvingId, setResolvingId] = useState(null)
  const [resolveError, setResolveError] = useState(null)

  useEffect(() => {
    api.getDedupReview().then(setItems).catch((err) => setError(err.message))
  }, [])

  async function resolve(reviewId, decision) {
    setResolvingId(reviewId)
    setResolveError(null)
    try {
      await api.resolveDedupReview(reviewId, decision)
      // Remove from view without a full reload -- the backend already
      // confirmed the item left the pending queue (Phase 2's own real
      // verification showed this); trust that and update local state.
      setItems((prev) => prev.filter((item) => item.review_id !== reviewId))
    } catch (err) {
      setResolveError(err.message)
    } finally {
      setResolvingId(null)
    }
  }

  if (error) return <p className="hint-error">Could not load dedup review queue: {error}</p>
  if (!items) return <p>Loading...</p>

  return (
    <div>
      <h2>Duplicate-review queue</h2>
      {resolveError && <p className="hint-error">{resolveError}</p>}
      {items.length === 0 && <p className="hint-success">No pending duplicate-review items.</p>}
      {items.map((item) => (
        <div key={item.review_id} className="review-item">
          <p style={{ margin: 0 }}>
            <strong>{item.existing_vacancy.title}</strong> at {item.existing_vacancy.company_name}
            {item.existing_vacancy.location_text ? ` -- ${item.existing_vacancy.location_text}` : ''}
          </p>
          <p style={{ margin: '4px 0', fontSize: 13, color: '#666' }}>
            Incoming source: {item.incoming_source.source_id} ({item.incoming_source.source_url})
          </p>
          <p style={{ margin: '4px 0', fontSize: 13 }}>
            Confidence: <strong>{item.confidence !== null ? `${(item.confidence * 100).toFixed(1)}%` : 'n/a'}</strong>
            {' -- '}{item.decision_reason}
          </p>
          <div className="review-item-actions">
            <button type="button" disabled={resolvingId === item.review_id}
              onClick={() => resolve(item.review_id, 'duplicate')}>
              Duplicate
            </button>
            <button type="button" className="secondary" disabled={resolvingId === item.review_id}
              onClick={() => resolve(item.review_id, 'not_duplicate')}>
              Not a duplicate
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
