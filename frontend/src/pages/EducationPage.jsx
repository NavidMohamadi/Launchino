import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { Select, TextField, DateField } from '../components/formFields'
import SearchAutocomplete from '../components/SearchAutocomplete'

const LEVELS = ['secondary', 'vocational', 'bachelor', 'master', 'phd', 'other']
const STATUSES = ['completed', 'currently_studying', 'did_not_complete']

function blankEntry() {
  return {
    level: 'bachelor', institution: { ror_id: null, name: '' }, program: '',
    field: { isced_code: null, confidence: null }, start_date: null, end_date: null, status: 'completed',
  }
}

export default function EducationPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  // Keyed by entry index -- the mapped label + confidence for the program's
  // ISCED-F field, so the candidate sees what was matched, not just a code.
  const [programMappings, setProgramMappings] = useState({})

  useEffect(() => {
    api.getCandidateSurveyValues(talentId)
      .then((existing) => {
        const saved = existing['EDU-HISTORY']
        if (saved?.value?.entries?.length) setEntries(saved.value.entries)
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false))
  }, [talentId])

  function updateEntry(index, patch) {
    setEntries((prev) => prev.map((e, i) => (i === index ? { ...e, ...patch } : e)))
  }

  function removeEntry(index) {
    setEntries((prev) => prev.filter((_, i) => i !== index))
    setProgramMappings((prev) => { const next = { ...prev }; delete next[index]; return next })
  }

  async function mapProgramField(index, programText) {
    if (!programText || !programText.trim()) return
    try {
      const result = await api.mapProgram(talentId, programText)
      updateEntry(index, {
        field: { isced_code: result.matched_code, confidence: result.confidence },
      })
      setProgramMappings((prev) => ({ ...prev, [index]: result }))
    } catch {
      // Mapping is a best-effort enrichment, not a blocker -- the raw programme
      // text is still saved either way, just without an ISCED-F code.
    }
  }

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

        {entries.map((entry, index) => {
          const mapping = programMappings[index]
          return (
            <div key={index} className="entry-card">
              <button type="button" className="entry-card-remove" onClick={() => removeEntry(index)}>Remove</button>
              <div className="field-group">
                <Select label="Level" value={entry.level} options={LEVELS} onChange={(v) => updateEntry(index, { level: v })} />
                <SearchAutocomplete
                  label="Institution" value={entry.institution.name}
                  searchFn={api.searchInstitutions}
                  getOptionLabel={(o) => o.name}
                  placeholder="Start typing your institution..."
                  onChange={(text, option) => updateEntry(index, { institution: { name: text, ror_id: option?.ror_id ?? null } })}
                />
                <SearchAutocomplete
                  label="Programme" value={entry.program}
                  searchFn={api.searchPrograms}
                  getOptionLabel={(o) => o.name}
                  placeholder="Start typing your programme..."
                  onChange={(text) => updateEntry(index, { program: text })}
                  onBlur={(text) => mapProgramField(index, text)}
                />
                {mapping && (
                  <p className="confidence-flag">
                    {mapping.matched_label
                      ? `Matched field of study: ${mapping.matched_label}${mapping.requires_confirmation ? ' (please double-check this)' : ''}`
                      : 'Could not automatically classify this programme\'s field of study -- that\'s fine, it\'s still saved.'}
                  </p>
                )}
                <DateField label="Start date" value={entry.start_date} onChange={(v) => updateEntry(index, { start_date: v })} />
                <DateField label="End date" value={entry.end_date} onChange={(v) => updateEntry(index, { end_date: v })} />
                <Select label="Status" value={entry.status} options={STATUSES} onChange={(v) => updateEntry(index, { status: v })} />
              </div>
            </div>
          )
        })}

        <button type="button" onClick={() => setEntries((prev) => [...prev, blankEntry()])}>+ Add education</button>

        <div style={{ marginTop: 20 }}>
          <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
        </div>
        {submitError && <p className="hint-error">{submitError}</p>}
      </div>
    </div>
  )
}
