import { useEffect, useState } from 'react'
import { IconChevronDown, IconSparkles } from '@tabler/icons-react'
import * as api from '../api'

// Collapsed by default; auto-expands exactly once, on a genuinely
// first-ever dashboard visit (talent.dashboard_intro_seen === false at
// load), then marks it seen so it stays collapsed by default on every
// later visit -- still manually reopenable any time via the toggle. See
// PROJECT_NOTES.md for why this needs a real persisted flag rather than
// just checking overall_percent_complete === 0 (that stays true on every
// revisit until real progress is made, so it can't tell "first visit"
// from "tenth visit, still nothing saved"). Placed at the very top of the
// dashboard, above the profile-completion header -- see PROJECT_NOTES.md
// for why it moved here from below the Continue button.
export default function DashboardIntro({ talentId, introSeen }) {
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    if (!introSeen) {
      setExpanded(true)
      api.markDashboardIntroSeen(talentId).catch(() => {})
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      className="card"
      style={{ marginBottom: 24, padding: 0, overflow: 'hidden', border: '1px solid var(--ll-neutral-200)' }}
    >
      <button
        type="button" onClick={() => setExpanded((v) => !v)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          gap: 12, background: 'var(--ll-neutral-100)', border: 'none', padding: '16px 20px',
          cursor: 'pointer', textAlign: 'left',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconSparkles size={20} color="var(--ll-turquoise-dark)" />
          <span style={{ fontWeight: 700, fontSize: 16, color: 'var(--ll-navy)' }}>What Launchino does for you</span>
        </span>
        <IconChevronDown
          size={20}
          style={{ transition: 'transform 0.2s ease', transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', flexShrink: 0 }}
        />
      </button>
      {expanded && (
        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p>
            Most people never get the chance to properly map out what they&rsquo;re actually good at, what
            kind of work energizes them, and what environment lets them do their best work &mdash; you&rsquo;re
            often left guessing, or applying to whatever&rsquo;s available rather than what genuinely fits.
          </p>
          <p>
            Launchino is built to change that. As you work through these sections, you&rsquo;re not just
            filling in a form &mdash; you&rsquo;re building a clearer picture of your own professional self,
            often clarifying things you hadn&rsquo;t put into words before.
          </p>
          <p>
            Once your profile reflects who you really are, companies searching for talent can find and
            evaluate you based on real fit, not just keywords on a CV &mdash; completely free, always.
          </p>
          <p>
            And if you want to go further: Premium means we actively search and surface relevant vacancies
            that fit you as they appear, so you spend less time hunting and more time applying to roles that
            are actually worth your time.
          </p>
        </div>
      )}
    </div>
  )
}
