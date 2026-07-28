import { useMemo, useState } from 'react'
import * as api from '../api'
import ElementQuestion from '../components/ElementQuestion'
import { useFitDictionary } from '../hooks/useFitDictionary'
import { useAuth } from '../auth/AuthContext'

const MOT_MAX_SELECTIONS = 5

function blankAnswer(elementId, sourceType) {
  return { element_id: elementId, value: {}, value_status: 'answered', unknown_reason: null, not_scored_reason: null, source_type: sourceType, shareable_with_employer: false }
}

const STEPS = ['input', 'review', 'done']

export default function CandidateSurveyPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const [step, setStep] = useState('input') // input -> review -> done

  const [cvText, setCvText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [unmappedTerms, setUnmappedTerms] = useState([])
  const [reviewFlags, setReviewFlags] = useState([])

  const [answers, setAnswers] = useState({}) // element_id -> answer
  const [motChecked, setMotChecked] = useState([]) // element_ids explicitly checked in this session

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [submitResult, setSubmitResult] = useState(null)

  const candidateSelectedIds = useMemo(() => {
    const fromAnswers = Object.keys(answers).filter((id) => id.startsWith('MOT-'))
    return [...new Set([...motChecked, ...fromAnswers])]
  }, [motChecked, answers])

  const { elements, error: dictError } = useFitDictionary({ candidateSelectedIds })

  const updateAnswer = (elementId, next) => setAnswers((prev) => ({ ...prev, [elementId]: next }))

  async function handleExtract() {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await api.extractCv(talentId, cvText)
      const nextAnswers = {}
      for (const item of result.extracted_elements) {
        const v = item.value
        nextAnswers[v.element_id] = {
          element_id: v.element_id, value: v.value, value_status: v.value_status,
          unknown_reason: v.unknown_reason, not_scored_reason: v.not_scored_reason,
          source_type: 'ai_extraction', shareable_with_employer: false,
        }
      }
      setAnswers(nextAnswers)
      setMotChecked(Object.keys(nextAnswers).filter((id) => id.startsWith('MOT-')))
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
      const values = Object.values(answers).map((a) => ({
        element_id: a.element_id, value: a.value, value_status: a.value_status,
        unknown_reason: a.unknown_reason, not_scored_reason: a.not_scored_reason,
        source_type: a.source_type || 'self_report', shareable_with_employer: !!a.shareable_with_employer,
      }))
      const result = await api.submitCandidateSurvey(talentId, values)
      setSubmitResult(result)
      setStep('done')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (dictError) return <p className="hint-error">Could not load the Fit Dictionary: {dictError}</p>
  if (!elements) return <p>Loading questions...</p>

  const motElements = (elements || []).filter((e) => e.category === 'MOT')
  const otherElements = (elements || []).filter((e) => e.category !== 'MOT' && (e.active || answers[e.element_id]))
  const stepIndex = STEPS.indexOf(step)

  return (
    <div>
      <h1>Your profile survey</h1>
      <div className="ll-step-progress">
        {STEPS.map((s, i) => (
          <div key={s} className={`ll-step ${i < stepIndex ? 'done' : i === stepIndex ? 'active' : ''}`} />
        ))}
      </div>

      {step === 'input' && (
        <div className="card">
          <h2>1. Share your CV, or start from scratch</h2>
          <p>Candidate: <strong>{auth.profile.full_name}</strong> (<code>{talentId}</code>)</p>
          <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
            Paste your CV text and we'll pre-fill your answers — you'll still review and confirm everything before it's saved.
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
          <h2>2. Review and edit before confirming</h2>

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

          <h3 className="category-heading">Motivation — pick your top {MOT_MAX_SELECTIONS}</h3>
          <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)' }}>Selected: {motChecked.length}/{MOT_MAX_SELECTIONS}</p>
          {motElements.map((el) => (
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

          {['PRACT', 'ENV', 'CAREER', 'TEAM'].map((category) => {
            const inCategory = otherElements.filter((e) => e.category === category)
            if (!inCategory.length) return null
            return (
              <div key={category}>
                <h3 className="category-heading">{category}</h3>
                {inCategory.map((el) => (
                  <ElementQuestion key={el.element_id} element={el} side="candidate"
                    answer={answers[el.element_id] || blankAnswer(el.element_id, 'self_report')}
                    onChange={(a) => updateAnswer(el.element_id, a)} />
                ))}
              </div>
            )
          })}

          <div style={{ marginTop: 20 }}>
            <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </div>
      )}

      {step === 'done' && (
        <div className="card">
          <p className="hint-success">
            Nice work — saved {submitResult.values_stored} answers for candidate <code>{talentId}</code>. You're a step closer to your next role.
          </p>
        </div>
      )}
    </div>
  )
}
