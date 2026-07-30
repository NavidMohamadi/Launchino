import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { TextField, DateField } from '../components/formFields'

function blankJob() {
  return { job_title: '', esco_uri: null, confidence: null, start_date: null, end_date: null, current: false }
}

export default function TaskHistoryPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [jobs, setJobs] = useState([])
  const [totalYears, setTotalYears] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [mappings, setMappings] = useState({})

  function loadExisting() {
    return api.getCandidateSurveyValues(talentId).then((existing) => {
      const savedJobs = existing['TASK-EXPERIENCE']
      if (savedJobs?.value?.jobs?.length) setJobs(savedJobs.value.jobs)
      // TASK-YEARS is never submitted by this page -- it's computed
      // automatically server-side from TASK-EXPERIENCE's dates (see
      // src/task_years.py). Read back and displayed here, not
      // recalculated client-side, so there is only one real implementation
      // of that algorithm, not a second JS copy that could drift from it.
      const savedYears = existing['TASK-YEARS']
      setTotalYears(savedYears?.value_status === 'answered' ? savedYears.value.level : null)
    })
  }

  useEffect(() => {
    loadExisting().catch((err) => setLoadError(err.message)).finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [talentId])

  function updateJob(index, patch) {
    setJobs((prev) => prev.map((j, i) => (i === index ? { ...j, ...patch } : j)))
  }

  function removeJob(index) {
    setJobs((prev) => prev.filter((_, i) => i !== index))
    setMappings((prev) => { const next = { ...prev }; delete next[index]; return next })
  }

  async function mapJobTitle(index, titleText) {
    if (!titleText || !titleText.trim()) return
    try {
      const result = await api.mapOccupation(talentId, titleText)
      updateJob(index, { esco_uri: result.matched_code, confidence: result.confidence })
      setMappings((prev) => ({ ...prev, [index]: result }))
    } catch {
      // Best-effort enrichment -- the job title and dates are still saved either way.
    }
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.submitCandidateSurvey(talentId, [{
        element_id: 'TASK-EXPERIENCE', value: { jobs }, value_status: jobs.length ? 'answered' : 'unknown',
        unknown_reason: jobs.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }])
      await loadExisting() // pick up the freshly-computed TASK-YEARS before navigating away
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="hint-error">Could not load your work experience: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>Task History</h1>
      <div className="card">
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
          Add every job you want considered, with its dates. Total years of experience is calculated for you automatically -- it isn't something you fill in.
        </p>
        {totalYears !== null && (
          <p className="confidence-flag" style={{ color: 'var(--ll-navy)', fontWeight: 600 }}>
            Total years of experience (computed automatically): {totalYears}
          </p>
        )}

        {jobs.map((job, index) => {
          const mapping = mappings[index]
          return (
            <div key={index} className="entry-card">
              <button type="button" className="entry-card-remove" onClick={() => removeJob(index)}>Remove</button>
              <div className="field-group">
                <TextField
                  label="Job title" value={job.job_title} placeholder="e.g. Software Engineer"
                  onChange={(v) => updateJob(index, { job_title: v })}
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
                  I currently work here
                </label>
                {!job.current && (
                  <DateField label="End date" value={job.end_date} onChange={(v) => updateJob(index, { end_date: v })} />
                )}
              </div>
            </div>
          )
        })}

        <button type="button" onClick={() => setJobs((prev) => [...prev, blankJob()])}>+ Add job</button>

        <div style={{ marginTop: 20 }}>
          <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
        </div>
        {submitError && <p className="hint-error">{submitError}</p>}
      </div>
    </div>
  )
}
