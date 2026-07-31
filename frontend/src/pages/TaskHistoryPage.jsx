import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import TaskEntryEditor from '../components/TaskEntryEditor'

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

  if (loadError) return <p className="hint-error">Could not load what you've done: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>What you&rsquo;ve done</h1>
      <div className="card">
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
          Jobs, internships, projects &mdash; anything that shows what you can do. Total duration is calculated
          for you automatically -- it isn't something you fill in.
        </p>
        {totalYears !== null && (
          <p className="confidence-flag" style={{ color: 'var(--ll-navy)', fontWeight: 600 }}>
            Total years of experience (computed automatically): {totalYears}
          </p>
        )}

        <TaskEntryEditor talentId={talentId} jobs={jobs} onChange={setJobs} />

        <div style={{ marginTop: 20 }}>
          <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
        </div>
        {submitError && <p className="hint-error">{submitError}</p>}
      </div>
    </div>
  )
}
