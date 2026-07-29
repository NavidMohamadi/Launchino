import { useEffect, useState } from 'react'
import { IconStar } from '@tabler/icons-react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'

const PLANS = [
  { key: 'one_month', name: '1 month', price: '€25', period: '/ month', featured: false },
  { key: 'three_month', name: '3 months', price: '€50', period: '/ 3 months', featured: true },
]

export default function PremiumPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id

  const [pending, setPending] = useState(undefined) // undefined = loading, null = none, object = pending
  const [error, setError] = useState(null)
  const [submittingPlan, setSubmittingPlan] = useState(null)
  const [submitError, setSubmitError] = useState(null)
  const [justSubmitted, setJustSubmitted] = useState(false)

  useEffect(() => {
    api.getPremiumRequest(talentId).then(setPending).catch((err) => setError(err.message))
  }, [talentId])

  async function requestAccess(plan) {
    setSubmittingPlan(plan)
    setSubmitError(null)
    try {
      const result = await api.createPremiumRequest(talentId, plan)
      setPending(result)
      setJustSubmitted(true)
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmittingPlan(null)
    }
  }

  if (error) return <p className="hint-error">Could not load Premium: {error}</p>

  return (
    <div>
      <div className="ll-premium-header">
        <h1>Launchino Premium</h1>
        <p>Get proactive job matching -- we surface fit vacancies for you, instead of you searching for them.</p>
      </div>

      {pending && (
        <p className="ll-premium-pending">
          {justSubmitted
            ? 'Request sent, we’ll review it and follow up shortly.'
            : `You already have a pending Premium request (${pending.plan === 'one_month' ? '1 month' : '3 months'}).`}
        </p>
      )}

      {submitError && <p className="hint-error">{submitError}</p>}

      <div className="ll-premium-plans">
        {PLANS.map((plan) => (
          <div key={plan.key} className={`ll-premium-plan${plan.featured ? ' featured' : ''}`}>
            {plan.featured && <span className="ll-premium-plan-badge">Better value</span>}
            <h3>{plan.name}</h3>
            <div className="ll-premium-price">{plan.price} <span>{plan.period}</span></div>
            <button
              type="button" className={plan.featured ? 'bg-pro' : 'secondary'}
              disabled={pending !== null || submittingPlan !== null}
              onClick={() => requestAccess(plan.key)}
            >
              <IconStar size={15} style={{ verticalAlign: 'text-bottom', marginRight: 6 }} />
              {submittingPlan === plan.key ? 'Sending...' : 'Request access'}
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
