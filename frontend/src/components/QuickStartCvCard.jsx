import { useState } from 'react'
import * as api from '../api'
import { useFitDictionary } from '../hooks/useFitDictionary'
import ElementQuestion from './ElementQuestion'
import EducationEntryEditor from './EducationEntryEditor'
import { TextField } from './formFields'

function blankAnswer(elementId, sourceType) {
  return { element_id: elementId, value: {}, value_status: 'answered', unknown_reason: null, not_scored_reason: null, source_type: sourceType, shareable_with_employer: false }
}

// The one-time "paste your CV" step, shown at the very start of the
// candidate journey -- see PROJECT_NOTES.md for why this lives here (on the
// dashboard) rather than on any single category page: a CV extraction can
// only ever honestly answer Basic Info's phone, Education, and Practical
// fit (api/extraction_service.py's CV_EXTRACTION_CATEGORIES), and those are
// now three separate routes/pages, not one. One paste here reviews and
// saves all three together; the candidate never sees this offered again
// once any of the three has real data (see CandidateDashboardPage.jsx's
// visibility condition).
export default function QuickStartCvCard({ talentId, onDone }) {
  const [dismissed, setDismissed] = useState(false)
  const [stage, setStage] = useState('offer') // offer -> reviewing
  const [cvText, setCvText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [unmappedTerms, setUnmappedTerms] = useState([])
  const [reviewFlags, setReviewFlags] = useState([])

  const [phone, setPhone] = useState('')
  const [answers, setAnswers] = useState({}) // PRACT element_id -> answer
  const [eduEntries, setEduEntries] = useState([])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const { elements, error: dictError } = useFitDictionary({})
  const practElements = (elements || []).filter((e) => e.category === 'PRACT' && e.active)

  async function handleExtract() {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await api.extractCv(talentId, cvText)
      const categoryById = Object.fromEntries((elements || []).map((e) => [e.element_id, e.category]))
      const nextAnswers = {}
      for (const item of result.extracted_elements) {
        const v = item.value
        if (v.element_id === 'EDU-HISTORY') continue // handled separately below, not a PRACT answer
        if (categoryById[v.element_id] !== 'PRACT') continue
        nextAnswers[v.element_id] = {
          element_id: v.element_id, value: v.value, value_status: v.value_status,
          unknown_reason: v.unknown_reason, not_scored_reason: v.not_scored_reason,
          source_type: 'ai_extraction', shareable_with_employer: false,
        }
      }
      setAnswers(nextAnswers)
      const eduItem = result.extracted_elements.find((item) => item.value.element_id === 'EDU-HISTORY')
      setEduEntries(eduItem?.value.value?.entries || [])
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
      const practValues = practElements
        .map((el) => answers[el.element_id] || blankAnswer(el.element_id, 'self_report'))
        .map((a) => ({
          element_id: a.element_id, value: a.value, value_status: a.value_status,
          unknown_reason: a.unknown_reason, not_scored_reason: a.not_scored_reason,
          source_type: a.source_type || 'self_report', shareable_with_employer: !!a.shareable_with_employer,
        }))
      const eduValue = {
        element_id: 'EDU-HISTORY', value: { entries: eduEntries },
        value_status: eduEntries.length ? 'answered' : 'unknown',
        unknown_reason: eduEntries.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }
      await api.submitCandidateSurvey(talentId, [...practValues, eduValue])
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
            We'll pre-fill your phone number, education, and practical-fit answers from it --
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
          {dictError && <p className="hint-error">Could not load the Fit Dictionary: {dictError}</p>}
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

          <h3 className="category-heading">Practical fit</h3>
          {practElements.map((el) => (
            <ElementQuestion key={el.element_id} element={el} side="candidate"
              answer={answers[el.element_id] || blankAnswer(el.element_id, 'self_report')}
              onChange={(a) => setAnswers((prev) => ({ ...prev, [el.element_id]: a }))} />
          ))}

          <h3 className="category-heading">Education</h3>
          <EducationEntryEditor talentId={talentId} entries={eduEntries} onChange={setEduEntries} />

          <div style={{ marginTop: 20 }}>
            <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Saving…' : 'Confirm and save'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </>
      )}
    </div>
  )
}
