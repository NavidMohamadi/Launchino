import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  IconAddressBook, IconBolt, IconBriefcase, IconBuilding, IconChartBar, IconCheck, IconClock, IconEye, IconFlag,
  IconMapPin, IconQuote, IconSchool, IconStar, IconTools, IconUsers,
} from '@tabler/icons-react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { BASIC_INFO_PATH, surveyPathFor } from '../categorySlugs'
import QuickStartCvCard from '../components/QuickStartCvCard'

const CATEGORY_ICONS = {
  EDU: IconSchool,
  PRACT: IconMapPin,
  TEAM: IconUsers,
  CAREER: IconFlag,
  MOT: IconBolt,
  ENV: IconBuilding,
  CAP: IconTools,
  TASK: IconBriefcase,
}

const STATUS_LABELS = { complete: 'Complete', in_progress: 'In progress', not_started: 'Not started' }

export default function CandidateDashboardPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [completion, setCompletion] = useState(null)
  const [error, setError] = useState(null)

  const loadCompletion = () => api.getCandidateCompletion(talentId).then(setCompletion).catch((err) => setError(err.message))

  useEffect(() => {
    loadCompletion()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [talentId])

  if (error) return <p className="hint-error">Could not load your profile: {error}</p>
  if (!completion) return <p>Loading...</p>

  // Basic Info is deliberately not part of completion.categories (see
  // api/candidate_service.py's compute_candidate_completion) -- it's a plain
  // talent column, not a Fit Dictionary category, excluded from
  // overall_percent_complete. Still surfaced first here, as its own
  // synthetic "next incomplete" candidate, since it's the first real step
  // in the intended survey order (see PROJECT_NOTES.md's Phase 4 entry).
  const nextIncomplete = !completion.basic_info.complete
    ? { category: 'BASIC_INFO', label: completion.basic_info.label }
    : completion.categories.find((c) => c.status !== 'complete')
  const pathFor = (category) => (category === 'BASIC_INFO' ? BASIC_INFO_PATH : surveyPathFor(category))

  // Quick-start CV card: only at the very start of the journey -- once any
  // of the three things a CV can fill (phone, Education, Practical fit) has
  // real data, offering it again would just be confusing (see
  // PROJECT_NOTES.md for the bug this replaced).
  const eduStatus = completion.categories.find((c) => c.category === 'EDU')?.status
  const practStatus = completion.categories.find((c) => c.category === 'PRACT')?.status
  const showQuickStart = !completion.basic_info.complete && eduStatus === 'not_started' && practStatus === 'not_started'

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

      {showQuickStart && <QuickStartCvCard talentId={talentId} onDone={loadCompletion} />}

      <div className="ll-dash-grid">
        <div
          key="basic-info" className="ll-dash-card clickable"
          role="button" tabIndex={0} onClick={() => navigate(BASIC_INFO_PATH)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(BASIC_INFO_PATH) } }}
        >
          {completion.basic_info.complete && (
            <span className="ll-dash-card-badge complete"><IconCheck size={20} /></span>
          )}
          <div className="ll-dash-card-icon"><IconAddressBook size={20} /></div>
          <div className="ll-dash-card-label">{completion.basic_info.label}</div>
          <div className={`ll-dash-card-status ${completion.basic_info.complete ? 'complete' : 'not_started'}`}>
            {STATUS_LABELS[completion.basic_info.complete ? 'complete' : 'not_started']}
          </div>
        </div>

        {completion.categories.map((cat) => {
          const Icon = CATEGORY_ICONS[cat.category]
          const goToCategory = () => navigate(surveyPathFor(cat.category))
          return (
            <div
              key={cat.category} className="ll-dash-card clickable"
              role="button" tabIndex={0} onClick={goToCategory}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToCategory() } }}
            >
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
          onClick={() => navigate(pathFor(nextIncomplete.category))}
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
