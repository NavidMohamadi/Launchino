import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  IconAddressBook, IconBolt, IconBriefcase, IconBuilding, IconChartBar, IconCheck, IconClock, IconEye, IconFlag,
  IconMapPin, IconQuote, IconSchool, IconStar, IconTools, IconUsers,
} from '@tabler/icons-react'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { ACCOUNT_SETTINGS_PATH, surveyPathFor } from '../categorySlugs'
import QuickStartCvCard from '../components/QuickStartCvCard'
import DashboardIntro from '../components/DashboardIntro'

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

  // Account Settings is deliberately not part of completion.categories (see
  // api/candidate_service.py's compute_candidate_completion) -- it's a plain
  // talent column, not a Fit Dictionary category, excluded from
  // overall_percent_complete. It must ALSO never be part of the "next
  // incomplete" CTA below: `basic_info.complete` only reflects whether phone
  // is set, and phone is optional for most contact preferences, so a
  // candidate who never sets one would otherwise see "Continue: Account
  // Settings" forever, never advancing to Education/Practical fit/etc. even
  // after finishing all 8 real categories (see PROJECT_NOTES.md -- a real
  // regression, not the original design: Account Settings is reachable any
  // time via its own standalone card, never a blocking step in this queue).
  const nextIncomplete = completion.categories.find((c) => c.status !== 'complete')

  // Quick-start CV card: only at the very start of the journey -- once any
  // of the three things a CV can fill (phone, Education, "What you've
  // done") has real data, offering it again would just be confusing (see
  // PROJECT_NOTES.md for the bug this replaced, and for the 2026-07-31
  // scope revision from Practical fit to "What you've done"/TASK).
  const eduStatus = completion.categories.find((c) => c.category === 'EDU')?.status
  const taskStatus = completion.categories.find((c) => c.category === 'TASK')?.status
  const showQuickStart = !completion.basic_info.complete && eduStatus === 'not_started' && taskStatus === 'not_started'

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
          key="account-settings" className="ll-dash-card clickable"
          role="button" tabIndex={0} onClick={() => navigate(ACCOUNT_SETTINGS_PATH)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(ACCOUNT_SETTINGS_PATH) } }}
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
          onClick={() => navigate(surveyPathFor(nextIncomplete.category))}
        >
          Continue: {nextIncomplete.label}
        </button>
      ) : (
        <p className="hint-success" style={{ textAlign: 'center' }}>
          Your profile is fully complete across every category.
        </p>
      )}

      <DashboardIntro talentId={talentId} introSeen={completion.dashboard_intro_seen} />
    </div>
  )
}
