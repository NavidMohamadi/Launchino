import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import CvImportPanel from '../components/CvImportPanel'
import EducationEntryEditor from '../components/EducationEntryEditor'

export default function EducationPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    api.getCandidateSurveyValues(talentId)
      .then((existing) => {
        const saved = existing['EDU-HISTORY']
        if (saved?.value?.entries?.length) setEntries(saved.value.entries)
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false))
  }, [talentId])

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const value = entries.length ? { entries } : { entries: [] }
      await api.submitCandidateSurvey(talentId, [{
        element_id: 'EDU-HISTORY', value, value_status: entries.length ? 'answered' : 'unknown',
        unknown_reason: entries.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }])
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="hint-error">Could not load your education history: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>Education</h1>
      <div className="card">
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
          Add every degree or programme you want considered. Start typing an institution or programme name for suggestions -- or just type your own if it isn't listed.
        </p>

        <CvImportPanel
          talentId={talentId}
          onEducationExtracted={(extracted) => setEntries((prev) => [...prev, ...extracted])}
        />

        <EducationEntryEditor talentId={talentId} entries={entries} onChange={setEntries} />

        <div style={{ marginTop: 20 }}>
          <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
        </div>
        {submitError && <p className="hint-error">{submitError}</p>}
      </div>
    </div>
  )
}
