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

  // Shared by the page's own "Confirm and submit" and the CV import panel's
  // "Confirm and save" -- CV-imported entries must actually persist right
  // then, not just populate local state waiting for a second button click
  // the candidate has no reason to expect (see PROJECT_NOTES.md: a real
  // reported bug where CV-extracted education looked confirmed but wasn't
  // saved because only Task History/phone were, silently, by the panel).
  async function saveEducation(entriesToSave) {
    const value = entriesToSave.length ? { entries: entriesToSave } : { entries: [] }
    await api.submitCandidateSurvey(talentId, [{
      element_id: 'EDU-HISTORY', value, value_status: entriesToSave.length ? 'answered' : 'unknown',
      unknown_reason: entriesToSave.length ? null : 'candidate_not_answered',
      source_type: 'self_report', shareable_with_employer: false,
    }])
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await saveEducation(entries)
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCvEducationExtracted(extracted) {
    const merged = [...entries, ...extracted]
    setEntries(merged)
    await saveEducation(merged)
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
          onEducationExtracted={handleCvEducationExtracted}
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
