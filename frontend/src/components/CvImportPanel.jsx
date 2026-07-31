import { useState } from 'react'
import { IconChevronDown } from '@tabler/icons-react'
import * as api from '../api'
import EducationEntryEditor from './EducationEntryEditor'
import TaskEntryEditor from './TaskEntryEditor'
import { TextField } from './formFields'

// Embedded, opt-in CV import -- lives on the Education page (see
// EducationPage.jsx) rather than as a separate dashboard step, since a CV
// paste is fundamentally something a candidate does *while* filling in
// Education, not a gate before it (see PROJECT_NOTES.md for the earlier
// dashboard-step version this replaced). Extraction covers Education +
// "What you've done" together (api/extraction_service.py's
// CV_EXTRACTION_CATEGORIES = {EDU, TASK}) since one CV is the real source
// for both. All three -- phone, Task History, and Education -- are saved
// immediately on confirm here, via onEducationExtracted (an async callback
// the parent EducationPage owns, since it's the one with the rest of the
// candidate's Education entries to merge into): a candidate who closes the
// tab right after confirming must not lose data that looked saved (a real
// reported bug -- see PROJECT_NOTES.md -- when Education alone was left
// unsaved, waiting on a second, separate button click).
//
// Only shows the fields that actually land somewhere in the real profile
// (phone, Education, Task History) -- unmapped_terms/review_flags from the
// extraction response are deliberately not rendered here, since neither has
// anywhere in the profile to go (see PROJECT_NOTES.md).
export default function CvImportPanel({ talentId, onEducationExtracted }) {
  const [open, setOpen] = useState(false)
  const [stage, setStage] = useState('offer') // offer -> reviewing
  const [cvText, setCvText] = useState('')
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState(null)

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
      setStage('reviewing')
    } catch (err) {
      setExtractError(err.message)
    } finally {
      setExtracting(false)
    }
  }

  async function handleConfirm() {
    setSubmitting(true)
    setSubmitError(null)
    try {
      if (phone.trim()) {
        await api.updateBasicInfo(talentId, { phone: phone.trim() })
      }
      const taskValue = {
        element_id: 'TASK-EXPERIENCE', value: { jobs: taskJobs },
        value_status: taskJobs.length ? 'answered' : 'unknown',
        unknown_reason: taskJobs.length ? null : 'candidate_not_answered',
        source_type: 'self_report', shareable_with_employer: false,
      }
      await api.submitCandidateSurvey(talentId, [taskValue])
      await onEducationExtracted(eduEntries)
      setOpen(false)
      setStage('offer')
      setCvText('')
    } catch (err) {
      setSubmitError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ border: '1px solid var(--ll-neutral-200)', borderRadius: 'var(--ll-radius-md)', marginBottom: 20, overflow: 'hidden' }}>
      <button
        type="button" onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          background: 'var(--ll-neutral-100)', border: 'none', padding: '12px 16px', cursor: 'pointer',
          textAlign: 'left', fontWeight: 600, color: 'var(--ll-navy)',
        }}
      >
        <span>Have a CV? Paste it here to speed this up</span>
        <IconChevronDown size={18} style={{ transition: 'transform 0.2s ease', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }} />
      </button>

      {open && stage === 'offer' && (
        <div style={{ padding: 16 }}>
          <textarea className="cv-input" placeholder="Paste raw CV text here..." value={cvText} onChange={(e) => setCvText(e.target.value)} />
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button onClick={handleExtract} disabled={extracting || !cvText.trim()}>
              {extracting ? 'Reading your CV…' : 'Extract from CV'}
            </button>
          </div>
          {extractError && <p className="hint-error">Extraction failed: {extractError}</p>}
        </div>
      )}

      {open && stage === 'reviewing' && (
        <div style={{ padding: 16 }}>
          <p style={{ fontSize: 13, color: 'var(--ll-neutral-600)', marginBottom: 12 }}>
            Review and confirm what we found before it's saved to your profile.
          </p>

          <TextField label="Phone" value={phone} onChange={setPhone} placeholder="+31 6 1234 5678" />

          <h3 className="category-heading">Education</h3>
          <EducationEntryEditor talentId={talentId} entries={eduEntries} onChange={setEduEntries} />

          <h3 className="category-heading">What you&rsquo;ve done</h3>
          <TaskEntryEditor talentId={talentId} jobs={taskJobs} onChange={setTaskJobs} />

          <div style={{ marginTop: 20 }}>
            <button onClick={handleConfirm} disabled={submitting}>{submitting ? 'Saving…' : 'Confirm and save'}</button>
          </div>
          {submitError && <p className="hint-error">{submitError}</p>}
        </div>
      )}
    </div>
  )
}
