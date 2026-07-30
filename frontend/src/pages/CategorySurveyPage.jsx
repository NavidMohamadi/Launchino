import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import * as api from '../api'
import ElementQuestion from '../components/ElementQuestion'
import { useFitDictionary } from '../hooks/useFitDictionary'
import { useAuth } from '../auth/AuthContext'
import { SLUG_TO_CATEGORY } from '../categorySlugs'

const MOT_MAX_SELECTIONS = 5

const CATEGORY_LABELS = {
  PRACT: 'Practical fit',
  TEAM: 'How you work',
  CAREER: "Where you're headed",
  MOT: 'What drives you',
  ENV: 'Your ideal environment',
}

function blankAnswer(elementId, sourceType) {
  return { element_id: elementId, value: {}, value_status: 'answered', unknown_reason: null, not_scored_reason: null, source_type: sourceType, shareable_with_employer: false }
}

export default function CategorySurveyPage() {
  const { categorySlug } = useParams()
  const category = SLUG_TO_CATEGORY[categorySlug]

  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [step, setStep] = useState('input') // input -> review (submit navigates back to the dashboard, no in-page "done")
  const [cvText, setCvText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [unmappedTerms, setUnmappedTerms] = useState([])
  const [reviewFlags, setReviewFlags] = useState([])

  const [answers, setAnswers] = useState({}) // element_id -> answer, scoped to this category only
  const [motChecked, setMotChecked] = useState([])
  const [prefillLoaded, setPrefillLoaded] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  const candidateSelectedIds = useMemo(() => {
    const fromAnswers = Object.keys(answers).filter((id) => id.startsWith('MOT-'))
    return [...new Set([...motChecked, ...fromAnswers])]
  }, [motChecked, answers])

  const { elements, error: dictError } = useFitDictionary({ candidateSelectedIds })

  const updateAnswer = (elementId, next) => setAnswers((prev) => ({ ...prev, [elementId]: next }))

  // Pre-fills already-saved answers for this category (same mechanism as
  // before -- api/candidates/{id}/survey-values, see PROJECT_NOTES.md's
  // resume-answers fix). Scoped to this page's category once `elements` is
  // loaded, since survey-values returns every category's answers, not just
  // this one.
  useEffect(() => {
    if (!category) return
    api.getCandidateSurveyValues(talentId)
      .then((existing) => {
        setAnswers((prev) => ({ ...existing, ...prev }))
        const existingMotIds = Object.keys(existing).filter((id) => id.startsWith('MOT-'))
        if (existingMotIds.length) setMotChecked((prev) => [...new Set([...existingMotIds, ...prev])])
      })
      .catch(() => {})
      .finally(() => setPrefillLoaded(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [talentId, category])

  // Skip straight to the review step only if THIS category already has a
  // saved answer -- a candidate returning to continue/edit shouldn't have to
  // re-paste their CV. A category with nothing saved yet still gets the
  // CV-paste/skip-to-manual choice. (Previously this skip fired unconditionally
  // whenever a `focus` query param was present, and since the standalone
  // "Survey" nav link was removed, every remaining path into this page always
  // carried that param -- CV extraction had become unreachable through the
  // live UI. Gating on real per-category data fixes that, not just relocates it.)
  useEffect(() => {
    if (!elements || !prefillLoaded || !category) return
    const categoryElementIds = new Set(elements.filter((e) => e.category === category).map((e) => e.element_id))
    const hasExisting = Object.keys(answers).some((id) => categoryElementIds.has(id))
    if (hasExisting) setStep('review')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements, prefillLoaded, category])

  async function handleExtract() {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await api.extractCv(talentId, cvText)
      const categoryById = Object.fromEntries((elements || []).map((e) => [e.element_id, e.category]))
      const nextAnswers = {}
      for (const item of result.extracted_elements) {
        const v = item.value
        if (categoryById[v.element_id] !== category) continue // this page only reviews its own category
        nextAnswers[v.element_id] = {
          element_id: v.element_id, value: v.value, value_status: v.value_status,
          unknown_reason: v.unknown_reason, not_scored_reason: v.not_scored_reason,
          source_type: 'ai_extraction', shareable_with_employer: false,
        }
      }
      setAnswers((prev) => ({ ...prev, ...nextAnswers }))
      if (category === 'MOT') {
        setMotChecked((prev) => [...new Set([...prev, ...Object.keys(nextAnswers)])])
      }
      setUnmappedTerms(result.unmapped_terms || [])
      setReviewFlags(result.review_flags || [])
      setStep('review')
    } catch (err) {
      setExtractError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  function skipToManual() {
    setUnmappedTerms([])
    setReviewFlags([])
    setStep('review')
  }

  function toggleMot(elementId) {
    setMotChecked((prev) => {
      if (prev.includes(elementId)) {
        setAnswers((a) => { const next = { ...a }; delete next[elementId]; return next })
        return prev.filter((id) => id !== elementId)
      }
      if (prev.length >= MOT_MAX_SELECTIONS) return prev
      updateAnswer(elementId, blankAnswer(elementId, 'self_report'))
      return [...prev, elementId]
    })
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      // Scoped to this page's own category -- `answers` is prefilled from
      // GET .../survey-values, which returns EVERY category's saved answers
      // (see the prefill effect above), not just this page's. Submitting
      // the whole merged object would resubmit unrelated categories' data
      // on every save -- always wasteful, and actively broken once a
      // system-computed element existed (TASK-YEARS, Phase 4): any other
      // category's page would re-include it verbatim and the backend
      // correctly rejects a direct TASK-YEARS submission, so an unscoped
      // submit here would 400 on saving e.g. Practical fit alone.
      const categoryElementIds = new Set(categoryElements.map((e) => e.element_id))
      const values = Object.values(answers)
        .filter((a) => categoryElementIds.has(a.element_id))
        .map((a) => ({
          element_id: a.element_id, value: a.value, value_status: a.value_status,
          unknown_reason: a.unknown_reason, not_scored_reason: a.not_scored_reason,
          source_type: a.source_type || 'self_report', shareable_with_employer: !!a.shareable_with_employer,
        }))
      await api.submitCandidateSurvey(talentId, values)
      // Back to the dashboard, not an in-page "done" step -- the candidate
      // should immediately see this category's updated progress reflected.
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!category) return <Navigate to="/candidate" replace />
  if (dictError) return <p className="hint-error">Could not load the Fit Dictionary: {dictError}</p>
  if (!elements || !prefillLoaded) return <p>Loading questions...</p>

  // MOT's own checkbox is what makes an element active (CANDIDATE_SELECTED
  // policy) -- filtering on e.active here, before anything is ever checked,
  // would mean none of the 12 MOT elements could ever render. So MOT always
  // lists every element (same as the original single-page version); only the
  // other, ALWAYS-activated categories filter on e.active.
  const categoryElements = category === 'MOT'
    ? elements.filter((e) => e.category === 'MOT')
    : elements.filter((e) => e.category === category && (e.active || answers[e.element_id]))
  const label = CATEGORY_LABELS[category]

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>{label}</h1>

      {step === 'input' && (
        <div className="card">
          <h2>Share your CV, or start from scratch</h2>
          <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
            Paste your CV text and we'll pre-fill your answers for this section — you'll still review and confirm everything before it's saved.
          </p>
          <textarea className="cv-input" placeholder="Paste raw CV text here..." value={cvText} onChange={(e) => setCvText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button onClick={handleExtract} disabled={extracting || !cvText.trim()}>
              {extracting ? 'Reading your CV…' : 'Extract from CV'}
            </button>
            <button className="secondary" onClick={skipToManual}>Skip — fill in manually</button>
          </div>
          {extractError && <p className="hint-error">Extraction failed: {extractError}</p>}
        </div>
      )}

      {step === 'review' && (
        <div className="card">
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

          {category === 'MOT' ? (
            <>
              <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)' }}>Selected: {motChecked.length}/{MOT_MAX_SELECTIONS}</p>
              {categoryElements.map((el) => (
                <div key={el.element_id} className="element-question">
                  <label className="checkbox">
                    <input
                      type="checkbox" checked={motChecked.includes(el.element_id)}
                      disabled={!motChecked.includes(el.element_id) && motChecked.length >= MOT_MAX_SELECTIONS}
                      onChange={() => toggleMot(el.element_id)}
                    />
                    <strong>{el.label}</strong>
                  </label>
                  {el.active && (
                    <ElementQuestion element={el} side="candidate" answer={answers[el.element_id] || blankAnswer(el.element_id, 'self_report')}
                      onChange={(a) => updateAnswer(el.element_id, a)} />
                  )}
                </div>
              ))}
            </>
          ) : (
            categoryElements.map((el) => (
              <ElementQuestion key={el.element_id} element={el} side="candidate"
                answer={answers[el.element_id] || blankAnswer(el.element_id, 'self_report')}
                onChange={(a) => updateAnswer(el.element_id, a)} />
            ))
          )}

          <div style={{ marginTop: 20 }}>
            <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </div>
      )}
    </div>
  )
}
