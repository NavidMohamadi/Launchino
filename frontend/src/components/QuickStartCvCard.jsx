import { useState } from 'react'
import * as api from '../api'
import EducationEntryEditor from './EducationEntryEditor'
import TaskEntryEditor from './TaskEntryEditor'
import { TextField } from './formFields'

// The one-time "paste your CV" step, shown at the very start of the
// candidate journey -- see PROJECT_NOTES.md for why this lives here (on the
// dashboard) rather than on any single category page: a CV extraction can
// only ever honestly answer Basic Info's phone, Education, and "What
// you've done" (api/extraction_service.py's CV_EXTRACTION_CATEGORIES =
// {EDU, TASK} -- revised 2026-07-31, was {PRACT, EDU}: practical-fit facts
// like visa/sponsorship/location are exactly the kind of thing a candidate
// should state themselves, not have inferred from CV text), and those are
// three separate routes/pages, not one. One paste here reviews and saves
// all three together; the candidate never sees this offered again once any
// of the three has real data (see CandidateDashboardPage.jsx's visibility
// condition).
export default function QuickStartCvCard({ talentId, onDone }) {
  const [dismissed, setDismissed] = useState(false)
  const [stage, setStage] = useState('offer') // offer -> reviewing
  const [cvText, setCvText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [unmappedTerms, setUnmappedTerms] = useState([])
  const [reviewFlags, setReviewFlags] = useState([])

  const [phone, setPhone] = useState('')
  const [eduEntries, setEduEntries] = useState([])
  const [taskJobs, setTaskJobs] = useState([])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  async function handleExtract() {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await api.extractCv(talentId, cvText)
      const eduItem = result.extracted_elements.find((item) => item.value.element_id === 'EDU-HISTORY')
      const taskItem = result.extracted_elements.find((item) => item.value.element_id === 'TASK-EXPERIENCE')
      setEduEntries(eduItem?.value.value?.entries || [])
      setTaskJobs(taskItem?.value.value?.jobs || [])
      setPhone(result.basic_info?.phone || '')
      setUnmappedTerms(result.unmapped_terms || [])
      setReviewFlags(result.review_flags || [])
      setStage('reviewing')
    } catch (err) {
      setExtractError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      if (phone.trim()) {
        await api.updateBasicInfo(talentId, { phone: phone.trim() })
      }
      const eduValue = {
        element_id: 'EDU-HISTORY', value: { entries: eduEntries },
        value_status: eduEntries.length ? 'answered' : 'unknown',
        unknown_reason: eduEntries.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }
      const taskValue = {
        element_id: 'TASK-EXPERIENCE', value: { jobs: taskJobs },
        value_status: taskJobs.length ? 'answered' : 'unknown',
        unknown_reason: taskJobs.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }
      await api.submitCandidateSurvey(talentId, [eduValue, taskValue])
      onDone()
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (dismissed) return null

  return (
    <div className="card" style={{ marginBottom: 24 }}>
      {stage === 'offer' && (
        <>
          <h2>Quick start: paste your CV</h2>
          <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
            We'll pre-fill your phone number, education, and what you've done from it --
            you'll still review and confirm everything before it's saved.
          </p>
          <textarea className="cv-input" placeholder="Paste raw CV text here..." value={cvText} onChange={(e) => setCvText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button onClick={handleExtract} disabled={extracting || !cvText.trim()}>
              {extracting ? 'Reading your CV…' : 'Extract from CV'}
            </button>
            <button className="secondary" onClick={() => setDismissed(true)}>Skip -- I'll fill it in myself</button>
          </div>
          {extractError && <p className="hint-error">Extraction failed: {extractError}</p>}
        </>
      )}

      {stage === 'reviewing' && (
        <>
          <h2>Review and confirm</h2>

          {unmappedTerms.length > 0 && (
            <div className="unmapped-terms">
              <strong>Terms found in your CV we couldn't match yet:</strong>
              <ul>{unmappedTerms.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
          )}
          {reviewFlags.length > 0 && (
            <div className="unmapped-terms">
              <strong>Notes from extraction:</strong>
              <ul>{reviewFlags.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </div>
          )}

          <TextField label="Phone" value={phone} onChange={setPhone} placeholder="+31 6 1234 5678" />

          <h3 className="category-heading">Education</h3>
          <EducationEntryEditor talentId={talentId} entries={eduEntries} onChange={setEduEntries} />

          <h3 className="category-heading">What you&rsquo;ve done</h3>
          <TaskEntryEditor talentId={talentId} jobs={taskJobs} onChange={setTaskJobs} />

          <div style={{ marginTop: 20 }}>
            <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Saving…' : 'Confirm and save'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </>
      )}
    </div>
  )
}
