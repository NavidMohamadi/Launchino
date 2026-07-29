import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  IconBolt, IconBuilding, IconChartBar, IconCheck, IconClock, IconEye, IconFlag, IconMapPin, IconQuote, IconStar,
  IconUsers,
} from '@tabler/icons-react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'

const CATEGORY_ICONS = {
  PRACT: IconMapPin,
  TEAM: IconUsers,
  CAREER: IconFlag,
  MOT: IconBolt,
  ENV: IconBuilding,
}

const STATUS_LABELS = { complete: 'Complete', in_progress: 'In progress', not_started: 'Not started' }

export default function CandidateDashboardPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [completion, setCompletion] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getCandidateCompletion(talentId).then(setCompletion).catch((err) => setError(err.message))
  }, [talentId])

  if (error) return <p className="hint-error">Could not load your profile: {error}</p>
  if (!completion) return <p>Loading...</p>

  const nextIncomplete = completion.categories.find((c) => c.status !== 'complete')

  return (
    <div>
      <div className="ll-dash-header">
        <div>
          <h1>Your profile</h1>
          <p className="ll-dash-subhead">Get to know your professional self</p>
        </div>
        <div className="ll-dash-overall">
          {/* floor, not round -- must never display more progress than actually
              exists (e.g. a real 69.6% rounding up to a displayed "70%" right
              at the Premium-nudge threshold looked inconsistent with the
              nudge correctly staying hidden at that real value) */}
          <div className="ll-dash-overall-value">{Math.floor(completion.overall_percent_complete)}%</div>
          <div className="ll-dash-overall-label">complete</div>
        </div>
      </div>

      <div className="ll-dash-grid">
        {completion.categories.map((cat) => {
          const Icon = CATEGORY_ICONS[cat.category]
          return (
            <div key={cat.category} className="ll-dash-card">
              {cat.status === 'complete' && (
                <span className="ll-dash-card-badge complete"><IconCheck size={20} /></span>
              )}
              {cat.status === 'in_progress' && (
                <span className="ll-dash-card-badge in_progress">{Math.round(cat.percent_complete)}%</span>
              )}
              <div className="ll-dash-card-icon"><Icon size={20} /></div>
              <div className="ll-dash-card-label">{cat.label}</div>
              <div className={`ll-dash-card-status ${cat.status}`}>{STATUS_LABELS[cat.status]}</div>
            </div>
          )
        })}

        {/* Static preview of the future third-party feedback feature -- purely
            visual, no route/click behavior, and deliberately excluded from
            overall_percent_complete (that figure comes only from
            completion.categories above, untouched by this card). */}
        <div className="ll-dash-card inert">
          <span className="ll-dash-card-badge coming-soon">Coming soon</span>
          <div className="ll-dash-card-icon muted"><IconQuote size={20} /></div>
          <div className="ll-dash-card-label">How others see you</div>
          <div className="ll-dash-card-description">From family, friends &amp; colleagues</div>
        </div>
      </div>

      <hr className="ll-dash-divider" />

      <div className="ll-dash-valueprops">
        <div className="ll-dash-valueprop">
          <IconClock size={18} color="var(--ll-warning)" />
          <span>Great roles move fast, don&rsquo;t let an unfinished profile hold you back.</span>
        </div>
        <div className="ll-dash-valueprop">
          <IconEye size={18} color="var(--ll-success)" />
          <span>You&rsquo;re already visible to companies, from day one, completely free.</span>
        </div>
        <div className="ll-dash-valueprop">
          <IconChartBar size={18} color="var(--ll-turquoise-dark)" />
          <span>Finish it, and you&rsquo;ll be seen first, matched with real confidence.</span>
        </div>
        {completion.premium_ready && (
          <div className="ll-dash-valueprop">
            <IconStar size={18} color="var(--ll-purple)" />
            <span>Want proactive job matching? That&rsquo;s <Link to="/candidate/premium">Premium</Link></span>
          </div>
        )}
      </div>

      {nextIncomplete ? (
        <button
          type="button" className="ll-dash-cta"
          onClick={() => navigate(`/candidate/survey?focus=${nextIncomplete.category}`)}
        >
          Continue: {nextIncomplete.label}
        </button>
      ) : (
        <p className="hint-success" style={{ textAlign: 'center' }}>
          Your profile is fully complete across every category.
        </p>
      )}
    </div>
  )
}
