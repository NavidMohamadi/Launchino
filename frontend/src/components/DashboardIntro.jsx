import { useEffect, useState } from 'react'
import { IconChevronDown, IconChevronUp } from '@tabler/icons-react'
import * as api from '../api'

// Collapsed by default; auto-expands exactly once, on a genuinely
// first-ever dashboard visit (talent.dashboard_intro_seen === false at
// load), then marks it seen so it stays collapsed by default on every
// later visit -- still manually reopenable any time via the toggle. See
// PROJECT_NOTES.md for why this needs a real persisted flag rather than
// just checking overall_percent_complete === 0 (that stays true on every
// revisit until real progress is made, so it can't tell "first visit"
// from "tenth visit, still nothing saved").
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
    <div className="card" style={{ marginBottom: 24 }}>
      <button
        type="button" onClick={() => setExpanded((v) => !v)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left',
        }}
      >
        <h2 style={{ margin: 0 }}>What Launchino does for you</h2>
        {expanded ? <IconChevronUp size={20} /> : <IconChevronDown size={20} />}
      </button>
      {expanded && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
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
