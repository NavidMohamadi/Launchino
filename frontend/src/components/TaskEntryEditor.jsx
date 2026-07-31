import { useState } from 'react'
import * as api from '../api'
import { TextField, DateField } from './formFields'

export function blankTaskEntry() {
  return { job_title: '', employer: '', esco_uri: null, confidence: null, start_date: null, end_date: null, current: false }
}

// Simple start/end diff for THIS one entry -- not the same computation as
// TASK-YEARS' server-side overlap-merge total (src/task_years.py), which
// only matters once you're combining multiple ranges. A single entry needs
// no merge, so this doesn't risk becoming a second, drifting copy of that
// algorithm (see PROJECT_NOTES.md).
export function formatEntryDuration(startDate, endDate, current) {
  if (!startDate) return null
  const start = new Date(startDate)
  const end = current || !endDate ? new Date() : new Date(endDate)
  let months = (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth())
  if (months < 0) months = 0
  const years = Math.floor(months / 12)
  const remMonths = months % 12
  const parts = []
  if (years) parts.push(`${years} yr${years !== 1 ? 's' : ''}`)
  if (remMonths || !years) parts.push(`${remMonths} mo${remMonths !== 1 ? 's' : ''}`)
  return parts.join(' ')
}

// Shared between TaskHistoryPage.jsx ("What you've done", the standalone
// category page) and QuickStartCvCard.jsx (the one-time dashboard CV step) --
// same entry-editing UI, not two copies. Covers jobs, internships, and
// projects alike: employer/organization is free text, purely informational,
// never matched or mapped to anything (same pattern as Education's
// institution name) -- only job_title/"role or project name" gets a
// best-effort ESCO occupation mapping, and even that never blocks saving.
export default function TaskEntryEditor({ talentId, jobs, onChange }) {
  const [mappings, setMappings] = useState({})

  function updateJob(index, patch) {
    onChange(jobs.map((j, i) => (i === index ? { ...j, ...patch } : j)))
  }

  function removeJob(index) {
    onChange(jobs.filter((_, i) => i !== index))
    setMappings((prev) => { const next = { ...prev }; delete next[index]; return next })
  }

  async function mapJobTitle(index, titleText) {
    if (!titleText || !titleText.trim()) return
    try {
      const result = await api.mapOccupation(talentId, titleText)
      updateJob(index, { esco_uri: result.matched_code, confidence: result.confidence })
      setMappings((prev) => ({ ...prev, [index]: result }))
    } catch {
      // Best-effort enrichment -- the role/project name and dates are still saved either way.
    }
  }

  return (
    <>
      {jobs.map((job, index) => {
        const mapping = mappings[index]
        const duration = formatEntryDuration(job.start_date, job.end_date, job.current)
        return (
          <div key={index} className="entry-card">
            <button type="button" className="entry-card-remove" onClick={() => removeJob(index)}>Remove</button>
            <div className="field-group">
              <TextField
                label="Role or project name" value={job.job_title}
                placeholder="e.g. Software Engineer, or Capstone project: Traffic prediction model"
                onChange={(v) => updateJob(index, { job_title: v })}
              />
              <TextField
                label="Company or organization" value={job.employer || ''}
                placeholder="Company, university, or leave blank for personal projects"
                onChange={(v) => updateJob(index, { employer: v })}
              />
              <button type="button" onClick={() => mapJobTitle(index, job.job_title)} style={{ maxWidth: 160 }}>
                Check match
              </button>
              {mapping && (
                <p className="confidence-flag">
                  {mapping.matched_label
                    ? `Matched occupation: ${mapping.matched_label}${mapping.requires_confirmation ? ' (please double-check this)' : ''}`
                    : 'Could not automatically match this to a standard occupation -- that\'s fine, it\'s still saved.'}
                </p>
              )}
              <DateField label="Start date" value={job.start_date} onChange={(v) => updateJob(index, { start_date: v })} />
              <label className="checkbox">
                <input
                  type="checkbox" checked={job.current}
                  onChange={(e) => updateJob(index, { current: e.target.checked, end_date: e.target.checked ? null : job.end_date })}
                />
                I&rsquo;m still doing this
              </label>
              {!job.current && (
                <DateField label="End date" value={job.end_date} onChange={(v) => updateJob(index, { end_date: v })} />
              )}
              {duration && (
                <p className="confidence-flag" style={{ color: 'var(--ll-navy)', fontWeight: 600 }}>Duration: {duration}</p>
              )}
            </div>
          </div>
        )
      })}
      <button type="button" onClick={() => onChange([...jobs, blankTaskEntry()])}>+ Add entry</button>
    </>
  )
}
