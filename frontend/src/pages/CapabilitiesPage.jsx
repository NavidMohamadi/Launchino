import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import * as api from '../api'
import { useAuth } from '../auth/AuthContext'
import { Select, TextField } from '../components/formFields'

const LEVELS = ['beginner', 'intermediate', 'advanced', 'expert']

function blankSkill() {
  return { skill: '', level: 'intermediate', esco_uri: null, confidence: null }
}

export default function CapabilitiesPage() {
  const { auth } = useAuth()
  const talentId = auth.profile.talent_id
  const navigate = useNavigate()

  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [mappings, setMappings] = useState({}) // index -> MappingResult, for display only

  useEffect(() => {
    api.getCandidateSurveyValues(talentId)
      .then((existing) => {
        const saved = existing['CAP-SKILLS']
        if (saved?.value?.skills?.length) setSkills(saved.value.skills)
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false))
  }, [talentId])

  function updateSkill(index, patch) {
    setSkills((prev) => prev.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  function removeSkill(index) {
    setSkills((prev) => prev.filter((_, i) => i !== index))
    setMappings((prev) => { const next = { ...prev }; delete next[index]; return next })
  }

  async function mapSkillField(index, skillText) {
    if (!skillText || !skillText.trim()) return
    try {
      const result = await api.mapSkill(talentId, skillText)
      updateSkill(index, { esco_uri: result.matched_code, confidence: result.confidence })
      setMappings((prev) => ({ ...prev, [index]: result }))
    } catch {
      // Best-effort enrichment -- the skill and level are still saved either way.
    }
  }

  async function handleSubmit() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const value = { skills }
      await api.submitCandidateSurvey(talentId, [{
        element_id: 'CAP-SKILLS', value, value_status: skills.length ? 'answered' : 'unknown',
        unknown_reason: skills.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }])
      navigate('/candidate')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) return <p className="hint-error">Could not load your skills: {loadError}</p>
  if (loading) return <p>Loading...</p>

  return (
    <div>
      <p style={{ marginBottom: 16 }}>
        <Link to="/candidate">&larr; Back to your profile</Link>
      </p>
      <h1>Capabilities</h1>
      <div className="card">
        <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
          List every skill you want considered, and how you'd rate your own level in it.
        </p>

        {skills.map((entry, index) => {
          const mapping = mappings[index]
          return (
            <div key={index} className="entry-card">
              <button type="button" className="entry-card-remove" onClick={() => removeSkill(index)}>Remove</button>
              <div className="field-group">
                <TextField
                  label="Skill" value={entry.skill} placeholder="e.g. SQL, Project management, Adobe Photoshop"
                  onChange={(v) => updateSkill(index, { skill: v })}
                />
                <button type="button" onClick={() => mapSkillField(index, entry.skill)} style={{ maxWidth: 160 }}>
                  Check match
                </button>
                {mapping && (
                  <p className="confidence-flag">
                    {mapping.matched_label
                      ? `Matched: ${mapping.matched_label}${mapping.requires_confirmation ? ' (please double-check this)' : ''}`
                      : 'Could not automatically match this skill to a standard skill code -- that\'s fine, it\'s still saved.'}
                  </p>
                )}
                <Select label="Your level" value={entry.level} options={LEVELS} onChange={(v) => updateSkill(index, { level: v })} />
              </div>
            </div>
          )
        })}

        <button type="button" onClick={() => setSkills((prev) => [...prev, blankSkill()])}>+ Add skill</button>

        <div style={{ marginTop: 20 }}>
          <button onClick={handleSubmit} disabled={submitting}>{submitting ? 'Submitting…' : 'Confirm and submit'}</button>
        </div>
        {submitError && <p className="hint-error">{submitError}</p>}
      </div>
    </div>
  )
}
