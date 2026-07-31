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

// CV extraction is NOT offered here -- it's an opt-in panel embedded on the
// Education page (CvImportPanel.jsx, via EducationPage.jsx), covering only
// Education + "What you've done" (api/extraction_service.py's
// CV_EXTRACTION_CATEGORIES), since that's all a CV can ever honestly answer.
// TEAM/CAREER/MOT/ENV/PRACT never had anything a CV extraction could fill.
// (Previously this page offered "Share your CV" on all 5 of its routes --
// see PROJECT_NOTES.md for the real bug that caused that and why it's gone.)
export default function CategorySurveyPage() {
  const { categorySlug } = useParams()
  const category = SLUG_TO_CATEGORY[categorySlug]

  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

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

      <div className="card">
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
    </div>
  )
}
