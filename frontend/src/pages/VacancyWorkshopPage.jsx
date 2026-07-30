import { useState } from 'react'
import * as api from '../api'
import ElementQuestion from '../components/ElementQuestion'
import { useFitDictionary } from '../hooks/useFitDictionary'
import { useAuth } from '../auth/AuthContext'

// Same default category weights the backend itself falls back to
// (src/canonical_vacancy.py's DEFAULT_PUBLIC_WEIGHTS) -- not invented here.
// Equal weighting across all 8 real categories (2026-07-30 decision, see
// PROJECT_NOTES.md) -- this is only a starting point for a company's own
// vacancy, freely customizable from here, unlike the scraped-vacancy path
// where this default is never reviewed by anyone.
// Keep this in exact sync with that constant; there is no runtime
// single-sourcing between the two (see PROJECT_NOTES.md).
const DEFAULT_CATEGORY_WEIGHTS = { PRACT: 12.5, CAP: 12.5, TASK: 12.5, TEAM: 12.5, CAREER: 12.5, MOT: 12.5, ENV: 12.5, EDU: 12.5 }

function blankAnswer(elementId) {
  return { element_id: elementId, value: {}, value_status: 'answered', unknown_reason: null, not_scored_reason: null, source_type: 'job_description' }
}

export default function VacancyWorkshopPage() {
  const { auth } = useAuth()
  // A company may have multiple vacancies, so (unlike the candidate page) picking
  // which one is still a real choice -- create new, or continue an existing one.
  // Typing another company's vacancy_id here is harmless: the backend enforces
  // ownership (api/auth.py's check_vacancy_ownership) regardless of what's typed.
  const [step, setStep] = useState('identify') // identify -> input -> review -> done
  const [vacancyId, setVacancyId] = useState('')
  const [companyName, setCompanyName] = useState(auth.profile.display_name)
  const [title, setTitle] = useState('')
  const [descriptionText, setDescriptionText] = useState('')
  const [identifyError, setIdentifyError] = useState(null)

  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)
  const [unmappedTerms, setUnmappedTerms] = useState([])
  const [reviewFlags, setReviewFlags] = useState([])

  const [answers, setAnswers] = useState({})

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [submitResult, setSubmitResult] = useState(null)

  // The vacancy is already fully created (all ALWAYS + CANDIDATE_SELECTED elements are
  // not relevant here; vacancy side cares about ALWAYS + VACANCY_ACTIVATED elements).
  // We activate every VACANCY_ACTIVATED element up front so the company can workshop
  // any of them -- there's no earlier "vacancy answer" that gates them the way MOT does
  // on the candidate side, so there's nothing meaningful to gate on yet.
  const { elements, error: dictError } = useFitDictionary({})

  const updateAnswer = (elementId, next) => setAnswers((prev) => ({ ...prev, [elementId]: next }))

  async function handleCreateVacancy(e) {
    e.preventDefault()
    setIdentifyError(null)
    try {
      const vacancy = await api.createVacancy({
        company_name: companyName, title, description_text: descriptionText || title,
        category_weights: DEFAULT_CATEGORY_WEIGHTS,
      })
      setVacancyId(vacancy.vacancy_id)
      setStep('input')
    } catch (err) {
      setIdentifyError(err.message)
    }
  }

  function useExistingId(e) {
    e.preventDefault()
    if (vacancyId) setStep('input')
  }

  async function handleExtract() {
    setExtracting(true)
    setExtractError(null)
    try {
      const result = await api.extractVacancyDescription(vacancyId, descriptionText)
      const nextAnswers = {}
      for (const item of result.extracted_elements) {
        const v = item.value
        nextAnswers[v.element_id] = {
          element_id: v.element_id, value: v.value, value_status: v.value_status,
          unknown_reason: v.unknown_reason, not_scored_reason: v.not_scored_reason,
          source_type: 'job_description',
        }
      }
      setAnswers(nextAnswers)
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

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const values = Object.values(answers).map((a) => ({
        element_id: a.element_id, value: a.value, value_status: a.value_status,
        unknown_reason: a.unknown_reason, not_scored_reason: a.not_scored_reason,
        source_type: a.source_type || 'job_description',
      }))
      const result = await api.submitVacancyWorkshop(vacancyId, values)
      setSubmitResult(result)
      setStep('done')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (dictError) return <p className="hint-error">Could not load the Fit Dictionary: {dictError}</p>
  if (!elements && step !== 'identify') return <p>Loading questions...</p>

  const visibleElements = (elements || []).filter((e) => e.active || answers[e.element_id])
  // A real pre-existing bug found during Phase 5 (see PROJECT_NOTES.md): this
  // list omitted EDU entirely, which was harmless while EDU had no active
  // elements but would have silently hidden the whole Education requirement
  // section the moment EDU-HISTORY went live (Phase 4).
  const categories = ['PRACT', 'EDU', 'ENV', 'CAP', 'TASK', 'TEAM', 'CAREER', 'MOT']

  return (
    <div>
      <h1>Vacancy workshop</h1>

      {step === 'identify' && (
        <div className="card">
          <h2>1. Identify the vacancy</h2>
          <form onSubmit={handleCreateVacancy}>
            <label className="field">Company name
              <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} required />
            </label>
            <label className="field">Job title
              <input value={title} onChange={(e) => setTitle(e.target.value)} required />
            </label>
            <label className="field">Description (used for the vacancy record; you can extract from it next)
              <textarea className="cv-input" value={descriptionText} onChange={(e) => setDescriptionText(e.target.value)} />
            </label>
            <button type="submit">Create new vacancy</button>
          </form>
          <p style={{ margin: '16px 0 4px' }}>...or continue an existing vacancy:</p>
          <form onSubmit={useExistingId} style={{ display: 'flex', gap: 8 }}>
            <input placeholder="existing vacancy_id" value={vacancyId} onChange={(e) => setVacancyId(e.target.value)} />
            <button type="submit" className="secondary">Continue</button>
          </form>
          {identifyError && <p className="hint-error">{identifyError}</p>}
        </div>
      )}

      {step === 'input' && (
        <div className="card">
          <h2>2. Extract from the description, or fill in manually</h2>
          <p>Vacancy: <code>{vacancyId}</code></p>
          <textarea className="cv-input" placeholder="Paste the vacancy description here..." value={descriptionText} onChange={(e) => setDescriptionText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button onClick={handleExtract} disabled={extracting || !descriptionText.trim()}>
              {extracting ? 'Extracting...' : 'Extract from description'}
            </button>
            <button className="secondary" onClick={skipToManual}>Skip -- fill in manually</button>
          </div>
          {extractError && <p className="hint-error">Extraction failed: {extractError}</p>}
        </div>
      )}

      {step === 'review' && (
        <div className="card">
          <h2>3. Review and edit before confirming</h2>

          {unmappedTerms.length > 0 && (
            <div className="unmapped-terms">
              <strong>Terms found in the description with no Fit Dictionary match yet:</strong>
              <ul>{unmappedTerms.map((t) => <li key={t}>{t}</li>)}</ul>
            </div>
          )}
          {reviewFlags.length > 0 && (
            <div className="unmapped-terms">
              <strong>Notes from extraction:</strong>
              <ul>{reviewFlags.map((f, i) => <li key={i}>{f}</li>)}</ul>
            </div>
          )}

          {categories.map((category) => {
            const inCategory = visibleElements.filter((e) => e.category === category)
            if (!inCategory.length) return null
            return (
              <div key={category}>
                <h3 className="category-heading">{category}</h3>
                {inCategory.map((el) => (
                  <ElementQuestion key={el.element_id} element={el} side="vacancy"
                    answer={answers[el.element_id] || blankAnswer(el.element_id)}
                    onChange={(a) => updateAnswer(el.element_id, a)} />
                ))}
              </div>
            )
          })}

          <div style={{ marginTop: 20 }}>
            <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting...' : 'Confirm and submit'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </div>
      )}

      {step === 'done' && (
        <div className="card">
          <p className="hint-success">
            Saved {submitResult.values_stored} answers for vacancy <code>{vacancyId}</code>.
          </p>
        </div>
      )}
    </div>
  )
}
